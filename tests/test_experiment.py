"""Generated PCM signals test mechanics only; no human recordings or voice claims."""

import io
import json
import time
import wave
from threading import Event

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from voicefont.audio import extract_features, read_audio
from voicefont.calibration import CalibrationStore
from voicefont.experiment import ExperimentBusy, ExperimentError, ExperimentService, session_dataset
from voicefont.experiment_routes import create_experiment_router


def generated_signal(index):
    """Deterministic generated multitone/noise fixture, NOT a recorded voice."""
    rng = np.random.default_rng(index)
    time_axis = np.arange(8000) / 16000
    samples = 0.12 * np.sin(2 * np.pi * (180 + index * 17) * time_axis)
    samples += 0.04 * np.sin(2 * np.pi * (900 + index * 31) * time_axis)
    samples += rng.normal(0, 0.015, len(time_axis))
    stream = io.BytesIO()
    with wave.open(stream, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes((samples * 32767).astype("<i2").tobytes())
    return stream.getvalue()


def saved_session(tmp_path, count=8, duplicate=False):
    store = CalibrationStore(tmp_path / "profiles")
    session = store.create(name="GENERATED SIGNAL fixture — mechanics only", consent=True)
    for i, prompt in enumerate(store.corpus["prompts"][:count]):
        session = store.submit_take(
            session["id"], prompt["id"], f"take-{i}", generated_signal(0 if duplicate else i)
        )
    return store, session


def finished(service, job_id):
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        result = service.get(job_id)
        if result["status"] not in ("queued", "running"):
            return result
        time.sleep(0.03)
    pytest.fail("experiment did not finish within 90 seconds")


def test_selected_snapshot_uses_real_audio_features_and_deduplicates_hashes(tmp_path):
    store, session = saved_session(tmp_path)
    first_prompt = store.corpus["prompts"][0]["id"]
    session = store.submit_take(session["id"], first_prompt, "replacement", generated_signal(8))
    dataset = session_dataset(store, session)
    assert dataset.features.shape == (8, 16)
    assert read_audio(generated_signal(0)).sha256 not in dataset.recording_ids
    assert read_audio(generated_signal(8)).sha256 in dataset.recording_ids
    expected = extract_features(read_audio(generated_signal(8)))
    index = dataset.recording_ids.index(read_audio(generated_signal(8)).sha256)
    np.testing.assert_allclose(dataset.features[index], expected)


@pytest.mark.parametrize("consent", [False, None, 1, "true"])
def test_separate_explicit_consent_required_before_any_job(tmp_path, consent):
    store, session = saved_session(tmp_path)
    service = ExperimentService(store.profile_root)
    with pytest.raises(ExperimentError, match="consent"):
        service.start(session["id"], consent=consent)
    assert not list(service.root.glob("*/result.json"))
    assert not list(service.root.rglob("mlflow.db"))


@pytest.mark.parametrize("count,duplicate", [(0, False), (7, False), (8, True)])
def test_insufficient_distinct_originals_never_train(tmp_path, count, duplicate):
    store, session = saved_session(tmp_path, count, duplicate)
    service = ExperimentService(store.profile_root)
    with pytest.raises(ExperimentError, match="8 distinct"):
        service.start(session["id"], consent=True)
    assert not list(service.root.rglob("mlflow.db"))


def test_real_background_pipeline_persists_metrics_and_disjoint_split(tmp_path):
    store, session = saved_session(tmp_path, 12)
    service = ExperimentService(store.profile_root)
    job = service.start(session["id"], consent=True)
    result = finished(service, job["id"])
    assert result["status"] == "completed", result
    assert result["consent"]["asserted"] is True
    assert result["report"]["stages"][:3] == ["preprocess", "train", "evaluate"]
    metrics = result["report"]["metrics"]
    assert np.isfinite(metrics["validation_mse"])
    assert np.isfinite(metrics["baseline_mse"])
    split = result["dataset"]
    assert split["distinct_recordings"] == 12
    assert len(split["train_hashes"]) == 9
    assert len(split["heldout_hashes"]) == 3
    assert not set(split["train_hashes"]) & set(split["heldout_hashes"])
    assert result["gate_passed"] == (result["report"]["status"] == "published")
    assert "not" in result["limitations"].lower()
    assert str(tmp_path) not in json.dumps(result)
    restored = ExperimentService(store.profile_root).get(job["id"])
    assert restored == result
    from voicefont.tracking import LocalOnlyMLflowConfig, LocalOnlyTracking

    directory = service.root / job["id"]
    tracking = LocalOnlyTracking(
        LocalOnlyMLflowConfig(directory / "mlflow.db", directory / "artifacts")
    )
    tracked = tracking.client.get_run(result["report"]["run_id"])
    assert tracked.info.status == "FINISHED"
    assert tracked.data.metrics["validation_mse"] == metrics["validation_mse"]
    assert "calibration session" in tracked.data.tags["provenance"]


def test_one_job_only_and_worker_failure_is_safe_and_persistent(tmp_path, monkeypatch):
    store, session = saved_session(tmp_path)
    entered, release = Event(), Event()

    def blocked(*args, **kwargs):
        entered.set()
        assert release.wait(10)
        raise RuntimeError("PRIVATE local path /secret/recording.wav")

    monkeypatch.setattr("voicefont.experiment.session_dataset", blocked)
    service = ExperimentService(store.profile_root)
    job = service.start(session["id"], consent=True)
    try:
        assert entered.wait(5)
        with pytest.raises(ExperimentBusy):
            ExperimentService(store.profile_root).start(session["id"], consent=True)
    finally:
        release.set()
    result = finished(service, job["id"])
    assert result["status"] == "failed"
    assert "PRIVATE" not in json.dumps(result)
    assert "report" not in result
    assert ExperimentService(store.profile_root).get(job["id"]) == result


def test_corrupt_selected_audio_fails_without_training(tmp_path):
    store, session = saved_session(tmp_path)
    (store.root / session["id"] / "takes" / "take-0.wav").write_bytes(b"corrupt")
    service = ExperimentService(store.profile_root)
    result = finished(service, service.start(session["id"], consent=True)["id"])
    assert result["status"] == "failed"
    assert not list(service.root.rglob("mlflow.db"))


def test_duplicate_bytes_are_one_group_and_stale_selection_is_not_trained(tmp_path):
    store, session = saved_session(tmp_path, 9)
    first_prompt = store.corpus["prompts"][0]["id"]
    session = store.submit_take(session["id"], first_prompt, "duplicate", generated_signal(1))
    dataset = session_dataset(store, session)
    assert len(dataset.recording_ids) == 8
    assert len(set(dataset.recording_ids)) == 8


def test_interrupted_result_is_failed_on_restart_without_retraining(tmp_path):
    service = ExperimentService(tmp_path / "profiles")
    job_id = "b" * 32
    directory = service.root / job_id
    directory.mkdir()
    (directory / "result.json").write_text(
        json.dumps({"id": job_id, "schema_version": 1, "status": "running"}), encoding="utf-8"
    )
    restored = ExperimentService(tmp_path / "profiles").get(job_id)
    assert restored["status"] == "failed"
    assert "Interrupted" in restored["error"]
    assert not list(service.root.rglob("mlflow.db"))


def test_unsafe_result_and_hardlinked_storage_are_rejected(tmp_path):
    import os

    service = ExperimentService(tmp_path / "profiles")
    with pytest.raises(ExperimentError):
        service.get("../outside")
    job_id = "c" * 32
    directory = service.root / job_id
    directory.mkdir()
    target = directory / "result.json"
    target.write_text('{"status":NaN}', encoding="utf-8")
    with pytest.raises(ExperimentError):
        service.get(job_id)
    target.unlink()
    outside = tmp_path / "private.json"
    outside.write_text('{"private":"must not be read"}', encoding="utf-8")
    os.link(outside, target)
    with pytest.raises(ExperimentError, match="linked"):
        service.get(job_id)


def test_api_validates_consent_origin_ids_and_does_real_job(tmp_path):
    store, session = saved_session(tmp_path)
    app = FastAPI()
    app.include_router(create_experiment_router(store.profile_root))
    with TestClient(app) as client:
        assert client.get("/experiments/capabilities").json()["available"] is True
        for consent in (False, "true", 1, None):
            response = client.post(
                "/experiments", json={"session_id": session["id"], "consent": consent}
            )
            assert response.status_code == 422
        assert (
            client.post(
                "/experiments", json={"session_id": "../escape", "consent": True}
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/experiments",
                json={"session_id": session["id"], "consent": True},
                headers={"origin": "https://other.test"},
            ).status_code
            == 403
        )
        assert client.get("/experiments/not-an-id").status_code == 422
        assert client.get("/experiments/" + "a" * 32).status_code == 404
        response = client.post("/experiments", json={"session_id": session["id"], "consent": True})
        assert response.status_code == 202, response.text
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            result = client.get("/experiments/" + response.json()["id"]).json()
            if result["status"] not in ("queued", "running"):
                break
            time.sleep(0.03)
        assert result["status"] == "completed", result
        assert "baseline_mse" in result["report"]["metrics"]
