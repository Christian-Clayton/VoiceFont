"""Shared local JSON policy with normal speech inputs, no backend required."""

import pytest
from fastapi import Request

from voicefont.request_body import read_json
from voicefont.synthesis_routes import SpeechRequest


@pytest.mark.anyio
async def test_shared_reader_accepts_streamed_normal_speech():
    chunks = iter([b'{"voice_id":"voice",', b'"text":"Hello"}'])

    async def receive():
        chunk = next(chunks, None)
        return {"type": "http.request", "body": chunk or b"", "more_body": chunk is not None}

    request = Request(
        {"type": "http", "headers": [(b"content-type", b"application/json")]}, receive
    )
    body = await read_json(request, SpeechRequest)
    assert body.text == "Hello"
    assert body.voice_id == "voice"
