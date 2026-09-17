"""Bounded streaming request parsing shared by local product endpoints."""
from fastapi import HTTPException, Request
from pydantic import ValidationError

MAX_BODY_BYTES = 16 * 1024


async def read_body(request: Request, limit: int, types: tuple[str, ...]):
    if request.headers.get("content-type", "").split(";")[0].strip().lower() not in types:
        raise HTTPException(415, "send application/json or raw PCM WAV as required")
    length = request.headers.get("content-length")
    if length is not None:
        try:
            size = int(length)
        except ValueError:
            raise HTTPException(400, "invalid Content-Length") from None
        if size < 0:
            raise HTTPException(400, "invalid Content-Length")
        if size > limit:
            raise HTTPException(413, "request exceeds maximum bytes")
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > limit:
            raise HTTPException(413, "request exceeds maximum bytes")
        raw.extend(chunk)
    return bytes(raw)


async def read_json(request: Request, model):
    raw = await read_body(request, MAX_BODY_BYTES, ("application/json",))
    try:
        return model.model_validate_json(raw)
    except ValidationError:
        raise HTTPException(422, "invalid JSON body, fields or field types") from None


