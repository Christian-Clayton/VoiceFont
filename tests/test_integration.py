"""End-to-end VoiceFont pipeline integration test.

Exercises: synthetic WAV creation → audio validation → profile enrollment
→ tiny autoencoder training → MLflow tracking verification.

This validates the core ML pipeline works together using FastAPI TestClient
and temporary directories.
"""

import io
import json
import wave

import numpy as np
import pytest
from fastapi.testclient import TestClient

from voicefont.api import create_app
from voicefont.audio import extract_features, read_audio
from voicefont.pipeline import run_pipeline
from voicefont.registry import ProfileStore
from voicefont.tracking import LocalOnlyMLflowConfig, LocalOnlyTracking
from voicefont.training import TrainingConfig


def _make_synthetic_wav(frequency=440, sr=16000, duration=0.5, amplitude=0.3):
    """Create a mono 16-bit PCM WAV as bytes.

    Uses a pure sinusoid with known frequency; this is a deterministic
    acoustic fixture, not a recorded voice.
    """
    t = np.arange(int(sr * duration)) / sr
    samples = amplitude * np.sin(2 * np.pi * frequency * t)
    raw = np.rint(samples * 32767).astype("<i2").tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sr)
        wav.writeframes(raw)
    return buf.getvalue()


def test_full_pipeline_wav_to_mlflow(tmp_path):
    """Full pipeline: WAV → audio validation → profile → train → MLflow."""

    # ------------------------------------------------------------------
    # Step 1: Create synthetic WAV
    # ------------------------------------------------------------------
    wav_bytes = _make_synthetic_wav(frequency=440, duration=0.5)
    assert len(wav_bytes) > 44  # Has WAV header + PCM data

    # ------------------------------------------------------------------
    # Step 2: Audio validation via read_audio + extract_features
    # ------------------------------------------------------------------
    audio = read_audio(wav_bytes)
    assert audio.sample_rate == 16000
    assert audio.channels == 1
    assert audio.sample_width == 2
    assert audio.duration_seconds == pytest.approx(0.5, abs=0.01)
    assert audio.samples.shape == (8000,)
    assert audio.sha256  # Provenance hash is set

    features = extract_features(audio)
    assert features.shape == (16,)
    assert np.isfinite(features).all()
    assert np.linalg.norm(features) == pytest.approx(1.0)  # Unit normalized

    # Verify determinism: same input → same features
    features_again = extract_features(read_audio(wav_bytes))
    np.testing.assert_array_equal(features, features_again)

    # ------------------------------------------------------------------
    # Step 3: Create profile via FastAPI TestClient
    # ------------------------------------------------------------------
    profile_root = tmp_path / "profiles"
    with TestClient(create_app(profile_root)) as client:
        # Health check
        health = client.get("/health").json()
        assert health["status"] == "ok"
        assert health["local_only"] is True
        assert health["feature_version"] == "acoustic-v1"

        # Enroll profile
        response = client.post(
            "/profiles?voice_id=test-voice&name=Test+Voice&consent=true",
            content=wav_bytes,
            headers={"content-type": "audio/wav"},
        )
        assert response.status_code == 201, response.text
        profile = response.json()
        assert profile["voice_id"] == "test-voice"
        assert profile["name"] == "Test Voice"
        assert profile["schema_version"] == "1.0.0"
        assert profile["feature_version"] == "acoustic-v1"
        assert profile["consent"]["asserted"] is True
        assert len(profile["references"]) == 1
        assert profile["references"][0]["path"] == "references/original.wav"
        assert len(profile["features"]) == 16

        # Verify profile is stored and retrievable
        profiles = client.get("/profiles").json()
        assert len(profiles) == 1
        assert profiles[0]["voice_id"] == "test-voice"

        fetched = client.get("/profiles/test-voice").json()
        assert fetched == profile

        # Verify duplicate enrollment is rejected
        dup_response = client.post(
            "/profiles?voice_id=test-voice&name=Duplicate&consent=true",
            content=wav_bytes,
            headers={"content-type": "audio/wav"},
        )
        assert dup_response.status_code == 409

    # Verify profile on disk via ProfileStore directly
    store = ProfileStore(profile_root)
    stored = store.get("test-voice")
    assert stored.voice_id == "test-voice"
    assert stored.features == profile["features"]

    # ------------------------------------------------------------------
    # Step 4: Run training with tiny autoencoder
    # ------------------------------------------------------------------
    # Generate 20 synthetic WAVs across 5 recording groups (4 each)
    # to satisfy group-based train/validation split requirements.
    np.random.default_rng(42)
    all_features = []
    recording_ids = []
    for i in range(20):
        freq = 200 + i * 50  # Distinct frequencies for distinct features
        wav = _make_synthetic_wav(frequency=freq, duration=0.5)
        aud = read_audio(wav)
        feat = extract_features(aud)
        all_features.append(feat)
        recording_ids.append(f"recording-{i // 4}")

    features_matrix = np.array(all_features)
    assert features_matrix.shape == (20, 16)

    output_dir = tmp_path / "training_output"
    output_dir.mkdir()

    report = run_pipeline(
        features_matrix,
        recording_ids,
        output_dir=output_dir,
        provenance="Synthetic integration test — mechanical validation only",
        config=TrainingConfig(bottleneck=2, max_iter=50, seed=42, validation_fraction=0.25),
    )

    # ------------------------------------------------------------------
    # Step 5: Verify MLflow tracking
    # ------------------------------------------------------------------
    # Pipeline report structure
    assert "run_id" in report
    assert "stages" in report
    assert "status" in report
    assert "metrics" in report
    assert "durations" in report
    assert "dataset_sha256" in report

    # All core stages executed
    assert "preprocess" in report["stages"]
    assert "train" in report["stages"]
    assert "evaluate" in report["stages"]

    # Metrics are finite
    metrics = report["metrics"]
    assert np.isfinite(metrics["validation_mse"])
    assert np.isfinite(metrics["baseline_mse"])
    assert metrics["baseline_mse"] > 0

    # Timing was recorded for each stage
    for stage in report["stages"]:
        assert stage in report["durations"]
        assert report["durations"][stage] >= 0

    # Verify MLflow run directly via tracking client
    tracking = LocalOnlyTracking(
        LocalOnlyMLflowConfig(output_dir / "mlflow.db", output_dir / "artifacts")
    )

    run_info = tracking.client.get_run(report["run_id"])
    assert run_info.info.status == "FINISHED"
    assert run_info.data.tags["provenance"] == "Synthetic integration test — mechanical validation only"

    # Params logged correctly
    assert run_info.data.params["seed"] == "42"
    assert run_info.data.params["bottleneck"] == "2"
    assert run_info.data.params["max_iter"] == "50"

    # Metrics match report
    assert run_info.data.metrics["validation_mse"] == pytest.approx(metrics["validation_mse"])
    assert run_info.data.metrics["baseline_mse"] == pytest.approx(metrics["baseline_mse"])

    # Training loss history logged
    loss_history = tracking.client.get_metric_history(report["run_id"], "training_loss")
    assert len(loss_history) > 0
    assert all(np.isfinite(m.value) for m in loss_history)

    # Duration metrics logged
    for stage in report["stages"]:
        metric_name = f"duration_{stage}_s"
        assert metric_name in run_info.data.metrics
        history = tracking.client.get_metric_history(report["run_id"], metric_name)
        assert len(history) == 1

    # Dataset provenance hash logged as param
    assert run_info.data.params["dataset_sha256"] == report["dataset_sha256"]

    # If published, verify artifacts
    if report["status"] == "published":
        assert "publish" in report["stages"]
        assert report["model_version"] is not None

        artifacts = tracking.client.list_artifacts(report["run_id"], "model")
        artifact_paths = {a.path for a in artifacts}
        assert "model/model.npz" in artifact_paths
        assert "model/model.json" in artifact_paths

        # Verify model weights are loadable
        weights_path = tracking.client.download_artifacts(report["run_id"], "model/model.npz")
        with np.load(weights_path, allow_pickle=False) as data:
            assert data["w0"].shape == (16, 2)  # input_dim x bottleneck
            assert data["w1"].shape == (2, 16)  # bottleneck x input_dim

        # Verify metadata JSON
        meta_path = tracking.client.download_artifacts(report["run_id"], "model/model.json")
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        assert metadata["model_kind"] == "numeric_feature_reconstruction_autoencoder"
        assert metadata["run_id"] == report["run_id"]
        assert metadata["provenance"] == "Synthetic integration test — mechanical validation only"

        # Model version registered
        versions = tracking.client.search_model_versions(f"run_id='{report['run_id']}'")
        assert len(versions) == 1
        assert versions[0].version == report["model_version"]

    # Disclaimer is present
    assert "Not voice cloning" in report["disclaimer"]


def test_pipeline_rejects_insufficient_data(tmp_path):
    """Pipeline rejects training with too few recordings."""
    output_dir = tmp_path / "training_output"
    output_dir.mkdir()

    # Only 1 unique recording group — below MIN_TRAIN_RECORDINGS=2
    features = np.random.default_rng(0).normal(size=(4, 16))
    recording_ids = ["same-group"] * 4

    with pytest.raises(ValueError, match="recording"):
        run_pipeline(
            features,
            recording_ids,
            output_dir=output_dir,
            provenance="Synthetic integration test — negative path",
        )


def test_audio_validation_rejects_synthetic_silence(tmp_path):
    """Audio validation rejects silent WAVs."""
    from voicefont.audio import AudioError

    # Create a silent WAV
    samples = np.zeros(8000, dtype=np.float64)
    raw = np.rint(samples * 32767).astype("<i2").tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(raw)
    silent_wav = buf.getvalue()

    with pytest.raises(AudioError, match="silent"):
        read_audio(silent_wav)
