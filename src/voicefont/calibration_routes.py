"""Loopback-only calibration endpoints. No URL/path upload or cloud integration."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool

from .audio import MAX_FILE_BYTES, AudioError
from .calibration import CalibrationConflict, CalibrationError, CalibrationStore
from .registry import RegistryError
from .request_body import read_body as _body
from .request_body import read_json as _json


class StrictBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class CreateBody(StrictBody):
    name: str = Field(min_length=1, max_length=128)
    consent: StrictBool
    mode: Literal["full", "adaptive"] = "full"


class PromptBody(StrictBody):
    prompt_id: str = Field(min_length=1, max_length=64)


class SelectBody(PromptBody):
    take_id: str = Field(min_length=1, max_length=64)


class FinalizeBody(StrictBody):
    voice_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)


async def _same_origin(request: Request):
    origin = request.headers.get("origin")
    expected = f"{request.url.scheme}://{request.url.netloc}"
    if origin is not None and origin != expected:
        raise HTTPException(403, "cross-origin calibration access is not permitted")
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise HTTPException(403, "cross-site calibration access is not permitted")


async def _call(function, *args, **kwargs):
    try:
        return await run_in_threadpool(function, *args, **kwargs)
    except (CalibrationConflict, FileExistsError) as exc:
        raise HTTPException(
            409,
            str(exc)
            if isinstance(exc, CalibrationConflict)
            else "immutable identifier already exists",
        ) from None
    except FileNotFoundError:
        raise HTTPException(404, "session, take or profile not found") from None
    except AudioError as exc:
        raise HTTPException(
            422,
            f"{exc}. Record again in a quiet room; adjust microphone gain "
            "if silent or clipped, then save PCM WAV.",
        ) from None
    except (CalibrationError, RegistryError) as exc:
        raise HTTPException(422, str(exc)) from None
    except OSError:
        raise HTTPException(
            503, "local storage unavailable; keep your recording and retry"
        ) from None


def create_calibration_router(profile_root: str | Path, *, corpus: dict | None = None):
    store = CalibrationStore(profile_root, corpus=corpus)
    router = APIRouter(prefix="/calibration", dependencies=[Depends(_same_origin)])

    @router.get("/corpus")
    def get_corpus():
        return store.corpus

    @router.post("/sessions", status_code=201)
    async def create(request: Request):
        body = await _json(request, CreateBody)
        return await _call(store.create, **body.model_dump())

    @router.get("/sessions")
    async def listing():
        return await _call(store.list_sessions)

    @router.get("/sessions/{session_id}")
    async def get(session_id: str):
        return await _call(store.get, session_id)

    @router.get("/sessions/{session_id}/corpus")
    async def session_corpus(session_id: str):
        return await _call(store.get_corpus, session_id)

    @router.post("/sessions/{session_id}/takes")
    async def take(
        request: Request,
        session_id: str,
        prompt_id: Annotated[str, Query(min_length=1, max_length=64)],
        take_id: Annotated[str, Query(min_length=1, max_length=64)],
    ):
        raw = await _body(
            request, MAX_FILE_BYTES, ("audio/wav", "audio/x-wav", "application/octet-stream")
        )
        return await _call(store.submit_take, session_id, prompt_id, take_id, raw)

    @router.post("/sessions/{session_id}/select")
    async def select(request: Request, session_id: str):
        body = await _json(request, SelectBody)
        return await _call(store.select, session_id, body.prompt_id, body.take_id)

    @router.post("/sessions/{session_id}/skip")
    async def skip(request: Request, session_id: str):
        body = await _json(request, PromptBody)
        return await _call(store.skip, session_id, body.prompt_id)

    @router.get("/sessions/{session_id}/takes/{take_id}/audio")
    async def audio(session_id: str, take_id: str):
        raw = await _call(store.audio, session_id, take_id)
        return Response(raw, media_type="audio/wav", headers={"Cache-Control": "no-store"})

    @router.post("/sessions/{session_id}/finalize")
    async def finalize(request: Request, session_id: str):
        body = await _json(request, FinalizeBody)
        return await _call(store.finalize, session_id, **body.model_dump())

    @router.get("/sessions/{session_id}/export")
    async def export(session_id: str):
        archive = await _call(store.export, session_id)

        def chunks():
            try:
                while chunk := archive.read(64 * 1024):
                    yield chunk
            finally:
                archive.close()

        return StreamingResponse(
            chunks(),
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="calibration-{session_id}.zip"',
                "Cache-Control": "no-store",
            },
            background=BackgroundTask(archive.close),
        )

    return router
