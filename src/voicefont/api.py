"""Single-user loopback HTTP API. Raw WAV uploads only, never filesystem paths/URLs.

POST /profiles?voice_id=...&name=...&consent=true with audio/wav body enrolls.
POST /search?top_k=5 with audio/wav body searches acoustic descriptors.
GET /profiles, /profiles/{id}, /profiles/{id}/similar?top_k=5 inspect/search.
POST /speak submits to the same local synthesis queue as /synthesis/jobs.
This is not authenticated multi-user serving. Do not expose it outside loopback.
"""

from __future__ import annotations

import os
from dataclasses import asdict
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .audio import FEATURE_VERSION, MAX_FILE_BYTES, AudioError
from .registry import ProfileStore, RegistryError
from .request_body import read_json
from .synthesis_routes import SpeechRequest, invoke


def default_root() -> Path:
    return Path(os.environ.get("VOICEFONT_HOME", Path.home() / ".voicefont")) / "profiles"


def _mount_routers(app: FastAPI, store: ProfileStore) -> None:
    """Mount required product modules, failing loudly on broken installations."""
    from importlib import resources

    from fastapi.responses import HTMLResponse, RedirectResponse, Response

    from .calibration_routes import create_calibration_router
    from .experiment_routes import create_experiment_router
    from .synthesis_routes import create_synthesis_router

    assets = resources.files("voicefont") / "calibration_assets"
    app.include_router(create_calibration_router(store.root))
    app.include_router(create_experiment_router(store.root))
    speech_router = create_synthesis_router(store.root)
    app.state.synthesis_service = speech_router.synthesis_service
    app.include_router(speech_router)

    @app.get("/", include_in_schema=False)
    def index():
        return RedirectResponse("/calibrate")

    @app.get("/calibrate", include_in_schema=False)
    def calibrate_page():
        return HTMLResponse((assets / "index.html").read_text(encoding="utf-8"))

    @app.get("/calibration-assets/{name}", include_in_schema=False)
    def calibration_asset(name: str):
        allowed = {"app.js", "recorder.js", "wav.js", "styles.css", "experiments.js"}
        if name not in allowed or not (assets / name).is_file():
            raise HTTPException(404, "asset not found")
        media = "text/css" if name.endswith(".css") else "text/javascript"
        return Response((assets / name).read_bytes(), media_type=media)


def create_app(
    root: str | Path | None = None, *, max_upload_bytes: int = MAX_FILE_BYTES
) -> FastAPI:
    app = FastAPI(title="VoiceFont local acoustic baseline", version="0.1.0")
    store = ProfileStore(root if root is not None else default_root())
    app.state.store = store
    _mount_routers(app, store)
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]", "testserver"]
    )

    @app.middleware("http")
    async def local_browser_boundary(request: Request, call_next):
        # The bundled UI may mutate only its exact origin, never another port/site.
        origin = request.headers.get("origin")
        expected = f"{request.url.scheme}://{request.headers.get('host', '')}"
        if origin is not None and origin != expected:
            return JSONResponse(
                {"detail": "foreign browser origin is not allowed"}, status_code=403
            )
        if request.headers.get("sec-fetch-site") == "cross-site":
            return JSONResponse({"detail": "cross-site requests are not allowed"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; script-src 'self'; style-src 'self'; "
            "connect-src 'self'; media-src 'self' blob:; img-src 'self' data:; "
            "frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
        return response

    async def read_upload(request: Request) -> bytes:
        if request.headers.get("content-type", "").split(";")[0] not in (
            "audio/wav",
            "audio/x-wav",
            "application/octet-stream",
        ):
            raise HTTPException(415, "send raw PCM WAV with Content-Type: audio/wav")
        length = request.headers.get("content-length")
        if length:
            try:
                parsed_length = int(length)
            except ValueError:
                raise HTTPException(400, "invalid Content-Length") from None
            if parsed_length < 0:
                raise HTTPException(400, "invalid Content-Length")
            if parsed_length > max_upload_bytes:
                raise HTTPException(413, "upload exceeds maximum bytes")
        data = bytearray()
        async for chunk in request.stream():
            if len(data) + len(chunk) > max_upload_bytes:
                raise HTTPException(413, "upload exceeds maximum bytes")
            data.extend(chunk)
        return bytes(data)

    @app.exception_handler(AudioError)
    @app.exception_handler(RegistryError)
    async def invalid_input(request: Request, exc: ValueError):
        return JSONResponse({"detail": str(exc)}, status_code=422)

    @app.exception_handler(FileExistsError)
    async def conflict(request: Request, exc: FileExistsError):
        return JSONResponse({"detail": "profile already exists"}, status_code=409)

    @app.exception_handler(FileNotFoundError)
    async def not_found(request: Request, exc: FileNotFoundError):
        return JSONResponse({"detail": "profile not found"}, status_code=404)

    @app.get("/health")
    def health():
        synthesis_available = False
        try:
            from .synthesis import capabilities as synthesis_capabilities

            synthesis_available = bool(synthesis_capabilities().get("available"))
        except (ImportError, OSError):
            pass
        return {
            "status": "ok",
            "local_only": True,
            "feature_version": FEATURE_VERSION,
            "synthesis_available": synthesis_available,
        }

    @app.get("/profiles")
    def profiles():
        return [p.to_dict() for p in store.list_profiles()]

    @app.get("/profiles/{voice_id}")
    def inspect(voice_id: str):
        return store.get(voice_id).to_dict()

    @app.get("/profiles/{voice_id}/similar")
    def similar(voice_id: str, top_k: Annotated[int, Query(ge=1, le=100)] = 5):
        return [asdict(match) for match in store.search_by_id(voice_id, top_k=top_k)]

    @app.post("/profiles", status_code=201)
    async def enroll(
        request: Request,
        voice_id: Annotated[str, Query(max_length=64)],
        name: Annotated[str, Query(min_length=1, max_length=128)],
        consent: bool = False,
    ):
        if consent is not True:
            raise HTTPException(422, "explicit consent=true is required")
        raw = await read_upload(request)
        profile = await run_in_threadpool(
            store.enroll, raw, voice_id=voice_id, name=name, consent=consent
        )
        return profile.to_dict()

    @app.post("/search")
    async def search(request: Request, top_k: Annotated[int, Query(ge=1, le=100)] = 5):
        raw = await read_upload(request)
        matches = await run_in_threadpool(store.search, raw, top_k=top_k)
        return [asdict(match) for match in matches]

    @app.post("/speak", status_code=202)
    async def speak(request: Request):
        body = await read_json(request, SpeechRequest)
        return await run_in_threadpool(
            invoke, app.state.synthesis_service.submit, **body.model_dump()
        )

    return app
