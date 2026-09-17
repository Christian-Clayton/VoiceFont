"""Tone analysis is computed on every speech submission and stored on the job."""

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from voicefont.registry import ProfileStore
from voicefont.synthesis import SynthesisService
from voicefont.synthesis_routes import create_synthesis_router


class BoundaryBackend:
    def __init__(self, reference: bytes):
        self.reference = reference
        self.audio = reference  # Valid WAV, so downstream validation passes.

    def capability(self):
        return {"available": True, "backend": "test-boundary", "device": "cpu", "message": "Test"}

    def run(self, reference, text, speed, output, cancel):
        output.write_bytes(self.audio)


def wait_job(service, job_id):
    job = service.wait(job_id)
    assert job["status"] == "completed"
    return job


def setup(tmp_path, signal_wav):
    root = tmp_path / "profiles"
    audio_bytes = signal_wav()
    ProfileStore(root).enroll(audio_bytes, voice_id="signal", name="Signal", consent=True)
    service = SynthesisService(root, backend=BoundaryBackend(audio_bytes), queue_limit=2)
    app = FastAPI()
    app.include_router(create_synthesis_router(root, service=service))
    return service, TestClient(app)


def test_job_reports_tone_analysis_of_submitted_text(tmp_path, signal_wav):
    service, client = setup(tmp_path, signal_wav)
    response = client.post(
        "/synthesis/jobs", json={"voice_id": "signal", "text": "Are you ready? Hurry!"}
    )
    assert response.status_code == 202
    job = wait_job(service, response.json()["id"])
    assert "tone" in job
    assert job["tone"]["questions"] == 1
    assert job["tone"]["urgency"] > 0
    assert str(tmp_path) not in json.dumps(job)


def test_tone_endpoint_returns_analysis_without_synthesizing(tmp_path, signal_wav):
    service, client = setup(tmp_path, signal_wav)
    response = client.post("/synthesis/tone", json={"text": "Unfortunately this failed badly."})
    assert response.status_code == 200
    body = response.json()
    assert body["version"] == "tone-v1"
    assert body["valence"] < 0.5
    analysis = service.analyze("plain text")
    assert analysis["version"] == "tone-v1"
