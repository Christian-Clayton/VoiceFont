"""Single-user loopback HTTP API. Raw WAV uploads only, never filesystem paths/URLs.

POST /profiles?voice_id=...&name=...&consent=true with audio/wav body enrolls.
POST /search?top_k=5 with audio/wav body searches acoustic descriptors.
GET /profiles, /profiles/{id}, /profiles/{id}/similar?top_k=5 inspect/search.
POST /speak returns 503 because no genuine local synthesis backend is installed.
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


def default_root() -> Path:
    return Path(os.environ.get("VOICEFONT_HOME", Path.home() / ".voicefont")) / "profiles"


def create_app(
    root: str | Path | None = None, *, max_upload_bytes: int = MAX_FILE_BYTES
) -> FastAPI:
    app = FastAPI(title="VoiceFont local acoustic baseline", version="0.1.0")
    store = ProfileStore(root if root is not None else default_root())
    app.state.store = store
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]", "testserver"]
    )

    @app.middleware("http")
    async def local_browser_boundary(request: Request, call_next):
        # No browser origins are needed for the CLI/API slice; prevent cross-site calls.
        if request.headers.get("origin") is not None:
            return JSONResponse({"detail": "browser origins are not enabled"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
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
        return {
            "status": "ok",
            "local_only": True,
            "feature_version": FEATURE_VERSION,
            "synthesis_available": False,
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

    @app.post("/speak")
    def speak():
        raise HTTPException(503, "local synthesis unavailable; no TTS backend is installed")

    return app
