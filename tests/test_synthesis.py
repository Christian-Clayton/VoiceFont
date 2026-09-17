"""Boundary tests use signals; opt-in integration uses the official technical fixture."""

import json
import os
import threading
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from voicefont.registry import ProfileStore
from voicefont.synthesis import SynthesisError, SynthesisService, synthesis_capabilities
from voicefont.synthesis_routes import create_synthesis_router


class BoundaryBackend:
    """Controlled subprocess boundary, NOT evidence of neural synthesis."""

    def __init__(self, audio, fail=False, block=False):
        self.audio = audio
        self.fail = fail
        self.block = block
        self.started = threading.Event()
        self.stopped = threading.Event()

    def capability(self):
        return dict(available=True, backend="test-boundary", device="cpu", message="Test only")

    def run(self, reference, text, speed, output, cancel):
        self.started.set()
        if self.block:
            cancel.wait(5)
        self.stopped.set()
        if self.fail:
            raise RuntimeError("private text and C:/private/path must not escape")
        if not cancel.is_set():
            output.write_bytes(self.audio)


@pytest.fixture
def setup_service(tmp_path, signal_wav):
    root = tmp_path / "profiles"
    ProfileStore(root).enroll(signal_wav(), voice_id="signal", name="Signal", consent=True)
    backend = BoundaryBackend(signal_wav())
    service = SynthesisService(root, backend=backend, queue_limit=2)
    app = FastAPI()
    app.include_router(create_synthesis_router(root, service=service))
    with TestClient(app) as client:
        yield service, backend, client, root
    assert service.closed


def wait_job(service, job_id):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        result = service.get(job_id)
        if result["status"] in {"completed", "failed", "cancelled"}:
            return result
        time.sleep(0.02)
    pytest.fail("job did not reach terminal state")


def test_job_contract_and_download(setup_service):
    service, backend, client, root = setup_service
    response = client.post("/synthesis/jobs", json={"voice_id": "signal", "text": "Local test"})
    assert response.status_code == 202
    job = wait_job(service, response.json()["id"])
    assert job["status"] == "completed"
    assert set(job) == {"id", "status", "tone", "audio_url"}
    assert str(root) not in json.dumps(job)
    audio = client.get(job["audio_url"])
    assert audio.status_code == 200
    assert audio.headers["content-type"] == "audio/wav"
    assert audio.content == backend.audio


@pytest.mark.parametrize(
    "change",
    [
        {"text": " "},
        {"text": "a" * 1001},
        {"speed": 0.74},
        {"speed": 1.51},
        {"style": "happy"},
        {"voice_id": "../escape"},
        {"reference": "C:/private.wav"},
    ],
)
def test_invalid_requests_do_not_start_worker(setup_service, change):
    service, backend, client, _ = setup_service
    request = {"voice_id": "signal", "text": "test", **change}
    assert client.post("/synthesis/jobs", json=request).status_code == 422
    assert not backend.started.is_set()


def test_missing_or_revoked_consent_denied(setup_service):
    _, backend, client, root = setup_service
    assert (
        client.post("/synthesis/jobs", json={"voice_id": "missing", "text": "test"}).status_code
        == 404
    )
    path = root / "signal/profile.json"
    data = json.loads(path.read_text())
    data["consent"]["asserted"] = False
    path.write_text(json.dumps(data))
    assert (
        client.post("/synthesis/jobs", json={"voice_id": "signal", "text": "test"}).status_code
        == 422
    )
    assert not backend.started.is_set()


def test_bounded_queue_cancel_running_and_queued(setup_service):
    service, backend, client, _ = setup_service
    backend.block = True
    body = {"voice_id": "signal", "text": "test"}
    first = client.post("/synthesis/jobs", json=body).json()
    assert backend.started.wait(2)
    second = client.post("/synthesis/jobs", json=body).json()
    assert client.post("/synthesis/jobs", json=body).status_code == 429
    assert client.get(f"/synthesis/jobs/{first['id']}/audio").status_code == 409
    assert client.post(f"/synthesis/jobs/{second['id']}/cancel").json()["status"] == "cancelled"
    assert client.post(f"/synthesis/jobs/{first['id']}/cancel").json()["status"] == "cancelled"
    assert backend.stopped.is_set()
    assert wait_job(service, first["id"])["status"] == "cancelled"
    assert not list(service.output_root.rglob("*.wav"))


def test_failure_is_generic_and_has_no_audio(setup_service):
    service, backend, client, _ = setup_service
    backend.fail = True
    job = client.post("/synthesis/jobs", json={"voice_id": "signal", "text": "secret"}).json()
    result = wait_job(service, job["id"])
    assert result == {"id": job["id"], "status": "failed", "error": "Speech generation failed."}
    assert client.get(f"/synthesis/jobs/{job['id']}/audio").status_code == 409


def test_timeout_job_has_safe_error(setup_service):
    service, backend, client, _ = setup_service

    def timeout(*args):
        raise SynthesisError("private path", 504)

    backend.run = timeout
    job = client.post("/synthesis/jobs", json={"voice_id": "signal", "text": "test"}).json()
    assert wait_job(service, job["id"])["error"] == "Speech generation timed out."
    assert not list(service.output_root.rglob("*.wav"))


def test_shutdown_stops_running_worker(setup_service):
    service, backend, _, _ = setup_service
    backend.block = True
    job = service.submit(voice_id="signal", text="test")
    assert backend.started.wait(2)
    service.close()
    assert backend.stopped.is_set()
    assert service.get(job["id"])["status"] == "cancelled"
    assert not service.output_root.exists()


def test_unknown_job_and_foreign_origin(setup_service):
    _, _, client, _ = setup_service
    assert client.get("/synthesis/jobs/not-a-uuid").status_code == 404
    assert (
        client.post(
            "/synthesis/jobs",
            json={"voice_id": "signal", "text": "test"},
            headers={"origin": "https://evil.example"},
        ).status_code
        == 403
    )


def test_real_subprocess_timeout_kills_descendants(tmp_path, monkeypatch):
    """Real subprocess boundary test, not a speech-quality test."""
    import subprocess
    import sys

    from voicefont.synthesis import OpenVoiceBackend

    worker = tmp_path / "sleep_worker.py"
    marker = tmp_path / "child-survived.txt"
    child_code = f"import time,pathlib; time.sleep(3); pathlib.Path({str(marker)!r}).touch()"
    worker.write_text(
        "import subprocess,sys,time\n"
        "sys.stdin.buffer.read()\n"
        f"subprocess.Popen([sys.executable, '-c', {child_code!r}])\n"
        "time.sleep(60)\n"
    )
    config = dict(
        python=sys.executable, worker=str(worker), runtime_root=str(tmp_path), timeout_seconds=0.3
    )
    monkeypatch.setattr("voicefont.synthesis.load_runtime_config", lambda *args: config)
    processes = []
    real_popen = subprocess.Popen

    def track(*args, **kwargs):
        process = real_popen(*args, **kwargs)
        if args[0][0] == sys.executable:
            processes.append(process)
        return process

    monkeypatch.setattr("voicefont.synthesis.subprocess.Popen", track)
    with pytest.raises(SynthesisError, match="timed out"):
        OpenVoiceBackend().run(
            tmp_path / "reference.wav",
            "private text",
            1.0,
            tmp_path / "speech.wav",
            threading.Event(),
        )
    assert len(processes) == 1
    assert processes[0].poll() is not None
    assert "private text" not in str(processes[0].args)
    time.sleep(3.2)
    assert not marker.exists(), "descendant continued after timeout"


def test_queued_consent_revalidated_before_compute(setup_service):
    service, backend, _, root = setup_service
    backend.block = True
    first = service.submit(voice_id="signal", text="test")
    assert backend.started.wait(2)
    second = service.submit(voice_id="signal", text="test")
    profile = root / "signal/profile.json"
    data = json.loads(profile.read_text())
    data["consent"]["asserted"] = False
    profile.write_text(json.dumps(data))
    service.cancel(first["id"])
    assert wait_job(service, second["id"])["status"] == "failed"


def test_unavailable_config_has_no_paths(tmp_path):
    config = tmp_path / "absent.json"
    capability = synthesis_capabilities(config)
    assert capability["available"] is False
    assert str(tmp_path) not in json.dumps(capability)
    service = SynthesisService(tmp_path / "profiles", config_path=config)
    try:
        with pytest.raises(SynthesisError) as caught:
            service.submit(voice_id="missing", text="test")
        assert caught.value.status_code == 503
    finally:
        service.close()


@pytest.mark.parametrize("value", [[], None, "invalid", 42])
def test_non_object_config_reports_unavailable(tmp_path, value):
    config = tmp_path / "config.json"
    config.write_text(json.dumps(value), encoding="utf-8")
    assert synthesis_capabilities(config) == synthesis_capabilities(tmp_path / "missing.json")


@pytest.mark.parametrize("operation", ["iterdir", "unlink", "rmtree"])
@pytest.mark.parametrize("persistent", [False, True])
def test_cleanup_fault_releases_waiters_and_bounds_later_work(
    setup_service, monkeypatch, operation, persistent
):
    """Ordinary locked-file faults using disposable generated signals only."""
    import shutil

    service, backend, _, _ = setup_service
    release = threading.Event()
    original_run = backend.run
    calls = []

    def run(reference, text, speed, output, cancel):
        calls.append(output.parent)
        if len(calls) == 1:
            (output.parent / "scratch").mkdir()
            backend.started.set()
            assert release.wait(3)
        original_run(reference, text, speed, output, cancel)

    backend.run = run
    first = service.submit(voice_id="signal", text="private test text")
    assert backend.started.wait(2)
    second = service.submit(voice_id="signal", text="second test")
    directory = service.output_root / first["id"]
    original_iterdir, original_unlink, original_rmtree = Path.iterdir, Path.unlink, shutil.rmtree
    faults = []

    def fault():
        faults.append(True)
        raise PermissionError("locked C:/private/reference.wav private test text")

    def iterdir(path):
        if path == directory and operation == "iterdir" and not faults:
            fault()
        return original_iterdir(path)

    def unlink(path, *args, **kwargs):
        if path.parent == directory and path.name.startswith("reference"):
            if operation == "unlink" and not faults:
                fault()
        return original_unlink(path, *args, **kwargs)

    def rmtree(path, *args, **kwargs):
        path = Path(path)
        if path == directory / "scratch" and operation == "rmtree" and not faults:
            fault()
        if path == directory and persistent and faults:
            fault()
        return original_rmtree(path, *args, **kwargs)

    try:
        with monkeypatch.context() as patcher:
            patcher.setattr(Path, "iterdir", iterdir)
            patcher.setattr(Path, "unlink", unlink)
            patcher.setattr(shutil, "rmtree", rmtree)
            release.set()
            result = service.wait(first["id"], timeout=3)
            assert result == {
                "id": first["id"],
                "status": "failed",
                "error": "Speech temporary-file cleanup failed.",
            }
            with pytest.raises(SynthesisError, match="not ready"):
                service.audio(first["id"])
            later = service.wait(second["id"], timeout=3)
            assert later["status"] == ("failed" if persistent else "completed")
            if persistent:
                assert len(calls) == 1
                assert service.capability()["available"] is False
                with pytest.raises(SynthesisError) as caught:
                    service.submit(voice_id="signal", text="third test")
                assert caught.value.status_code == 503
                assert "private" not in json.dumps(later) + str(caught.value)
            else:
                assert not directory.exists()
                third = service.submit(voice_id="signal", text="third test")
                assert service.wait(third["id"], timeout=3)["status"] == "completed"
            assert len(faults) == (2 if persistent else 1)
    finally:
        release.set()
    service.close()
    assert not service.output_root.exists()


def test_shutdown_cleanup_failure_is_explicit_and_retryable(setup_service, monkeypatch):
    import shutil

    service, _, _, _ = setup_service
    original = shutil.rmtree

    def locked(path, *args, **kwargs):
        if Path(path) == service.output_root:
            raise PermissionError("locked C:/private/path")
        return original(path, *args, **kwargs)

    with monkeypatch.context() as patcher:
        patcher.setattr(shutil, "rmtree", locked)
        with pytest.raises(RuntimeError, match="^Speech shutdown cleanup is incomplete\\.$"):
            service.close()
    assert service.closed
    assert not service.capability()["available"]
    service.close()
    assert not service.output_root.exists()


@pytest.mark.skipif(
    os.environ.get("VOICEFONT_RUN_OPENVOICE_TEST") != "1",
    reason="Explicit heavy offline fixture test",
)
def test_real_offline_technical_fixture(tmp_path):
    """Official repository fixture only. No independent speaker release verified."""
    from voicefont.audio import read_audio

    service = SynthesisService(tmp_path / "profiles")
    started = time.monotonic()
    try:
        assert service.capability()["available"] is True
        job = service.submit_technical_fixture(
            text="This is a local speech test. No cloud service is used."
        )
        assert service.wait(job["id"], timeout=190)["status"] == "completed"
        app = FastAPI()
        app.include_router(create_synthesis_router(tmp_path / "profiles", service=service))
        with TestClient(app) as client:
            status = client.get(f"/synthesis/jobs/{job['id']}").json()
            response = client.get(status["audio_url"])
            assert response.status_code == 200
            assert response.headers["content-type"] == "audio/wav"
            raw = response.content
        audio = read_audio(raw)
        assert audio.duration_seconds > 1
        assert audio.sample_rate == 22050
        assert not (tmp_path / "profiles").exists()
        evidence = Path(__file__).resolve().parents[1] / "data/openvoice-runtime/verification"
        evidence.mkdir(parents=True, exist_ok=True)
        (evidence / "technical-fixture.wav").write_bytes(raw)
        (evidence / "result.json").write_text(
            json.dumps(
                {
                    "job": service.get(job["id"]),
                    "duration_seconds": audio.duration_seconds,
                    "sample_rate": audio.sample_rate,
                    "sha256": audio.sha256,
                    "elapsed_seconds": time.monotonic() - started,
                    "technical_fixture_only": True,
                    "speaker_release_independently_verified": False,
                    "offline_python_network_blocked": True,
                },
                indent=2,
            )
        )
    finally:
        service.close()
