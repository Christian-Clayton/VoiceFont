"""HTTP job boundary. No paths, commands or technical-fixture bypass accepted."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from .request_body import read_json
from .synthesis import SynthesisError, SynthesisService


class ToneRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    text: str = Field(min_length=1, max_length=1000)


class SpeechRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    voice_id: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    text: str = Field(min_length=1, max_length=1000)
    style: Literal["neutral"] = "neutral"
    speed: float = Field(default=1.0, ge=0.75, le=1.5, allow_inf_nan=False)


async def same_origin(request: Request):
    origin = request.headers.get("origin")
    if origin is not None:
        expected = urlsplit(str(request.base_url))
        given = urlsplit(origin)
        if (given.scheme, given.netloc) != (expected.scheme, expected.netloc):
            raise HTTPException(403, "Foreign browser origins are not permitted.")
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise HTTPException(403, "Cross-site requests are not permitted.")


def invoke(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except SynthesisError as exc:
        raise HTTPException(exc.status_code, str(exc)) from None


def create_synthesis_router(
    profile_root: str | Path,
    *,
    service: SynthesisService | None = None,
    config_path: str | Path | None = None,
) -> APIRouter:
    service = service or SynthesisService(profile_root, config_path=config_path)

    @asynccontextmanager
    async def lifespan(app):
        try:
            yield
        finally:
            await run_in_threadpool(service.close)

    router = APIRouter(prefix="/synthesis", lifespan=lifespan, dependencies=[Depends(same_origin)])
    # Parent may use the same bounded service for POST /speak compatibility.
    router.synthesis_service = service

    @router.get("/capabilities")
    def capabilities():
        return service.capability()

    @router.post("/tone")
    async def tone(request: Request):
        body = await read_json(request, ToneRequest)
        return await run_in_threadpool(service.analyze, body.text)

    @router.post("/jobs", status_code=202)
    async def submit(request: Request):
        body = await read_json(request, SpeechRequest)
        return await run_in_threadpool(invoke, service.submit, **body.model_dump())

    @router.get("/jobs/{job_id}")
    def status(job_id: str):
        return invoke(service.get, job_id)

    @router.post("/jobs/{job_id}/cancel")
    def cancel(job_id: str):
        return invoke(service.cancel, job_id)

    @router.get("/jobs/{job_id}/audio")
    def audio(job_id: str):
        return Response(
            invoke(service.audio, job_id),
            media_type="audio/wav",
            headers={
                "Cache-Control": "no-store",
                "Content-Disposition": 'inline; filename="speech.wav"',
                "X-Content-Type-Options": "nosniff",
            },
        )

    return router
