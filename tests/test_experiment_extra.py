"""Tests targeting missing experiment.py lines: 58, 102, 120, 123, 207, 262, 266, 350-351."""

import time
from unittest.mock import MagicMock, patch

import pytest

from voicefont.calibration import CalibrationStore
from voicefont.experiment import ExperimentError, ExperimentService, _safe


def test_safe_rejects_symlink_experiment_storage(tmp_path):
    """Line 58: _safe rejects symlinks."""
    target = tmp_path / "experiments"
    target.mkdir()
    with patch("voicefont.experiment.Path.is_symlink", return_value=True):
        with pytest.raises(ExperimentError, match="linked"):
            _safe(target)


def test_safe_rejects_hardlinked_file(tmp_path):
    """Line 59: _safe rejects hardlinked experiment files.

    Note: On Windows, Path methods are read-only so we mock at the module level.
    """
    target = tmp_path / "linked_file"
    target.write_bytes(b"data")
    # Patch class methods at module level
    with patch("voicefont.experiment.Path.is_symlink", return_value=False):
        with patch("voicefont.experiment.Path.is_file", return_value=True):
            mock_stat = MagicMock()
            mock_stat.st_nlink = 2
            with patch("voicefont.experiment.Path.stat", return_value=mock_stat):
                with pytest.raises(ExperimentError, match="linked"):
                    _safe(target)


def test_exceeding_max_recordings_or_audio_seconds(tmp_path):
    """Line 102: too many recordings or too many total seconds."""
    store = CalibrationStore(tmp_path / "profiles")
    session = store.create(name="Signal fixture", consent=True)
    for i in range(8):
        raw = _signal_wav(i)
        session = store.submit_take(session["id"], store.corpus["prompts"][i]["id"], f"take-{i}", raw)

    with patch("voicefont.experiment.MAX_RECORDINGS", 2):
        from voicefont.experiment import session_dataset
        with pytest.raises(ExperimentError, match="bounded experiment size"):
            session_dataset(store, session)


def test_exceeding_byte_limit(tmp_path):
    """Line 120: total audio bytes exceed limit."""
    store = CalibrationStore(tmp_path / "profiles")
    session = store.create(name="Signal fixture", consent=True)
    for i in range(8):
        raw = _signal_wav(i)
        session = store.submit_take(session["id"], store.corpus["prompts"][i]["id"], f"take-{i}", raw)

    with patch("voicefont.experiment.MAX_AUDIO_BYTES", 100):
        from voicefont.experiment import session_dataset
        with pytest.raises(ExperimentError, match="byte limit"):
            session_dataset(store, session)


def test_audio_changed_after_consent(tmp_path):
    """Line 123: hash mismatch between stored audio and selected take."""
    store = CalibrationStore(tmp_path / "profiles")
    session = store.create(name="Signal fixture", consent=True)
    for i in range(8):
        raw = _signal_wav(i)
        session = store.submit_take(session["id"], store.corpus["prompts"][i]["id"], f"take-{i}", raw)

    # Mock store.audio to return different bytes than the original
    def tampered_audio(session_id, take_id):
        return _signal_wav(999)  # Different audio content
    store.audio = tampered_audio

    from voicefont.experiment import session_dataset
    with pytest.raises(ExperimentError, match="changed after consent"):
        session_dataset(store, session)


def test_result_exceeds_size_limit(tmp_path):
    """Line 207: oversized experiment result rejected on save."""
    service = ExperimentService(tmp_path / "profiles")
    job_id = "d" * 32
    directory = service.root / job_id
    directory.mkdir()

    result = {
        "id": job_id,
        "schema_version": 1,
        "status": "completed",
        "created_at": "2024-01-01T00:00:00+00:00",
        "updated_at": "2024-01-01T00:00:00+00:00",
        "report": {"data": "x" * (300 * 1024)},
    }
    with pytest.raises(ExperimentError, match="size limit"):
        service._save(result)


def test_ml_dependencies_not_installed(tmp_path):
    """Line 262: capabilities check rejects when ML deps missing."""
    store = CalibrationStore(tmp_path / "profiles")
    session = store.create(name="Signal fixture", consent=True)
    for i in range(8):
        raw = _signal_wav(i)
        session = store.submit_take(session["id"], store.corpus["prompts"][i]["id"], f"take-{i}", raw)

    with patch("voicefont.experiment.capabilities") as mock_caps:
        mock_caps.return_value = {"available": False}
        service = ExperimentService(store.profile_root)
        with pytest.raises(ExperimentError, match="not installed"):
            service.start(session["id"], consent=True)


def test_max_experiments_limit(tmp_path):
    """Line 266: too many experiments already exist."""
    store = CalibrationStore(tmp_path / "profiles")
    session = store.create(name="Signal fixture", consent=True)
    for i in range(8):
        raw = _signal_wav(i)
        session = store.submit_take(session["id"], store.corpus["prompts"][i]["id"], f"take-{i}", raw)

    service = ExperimentService(store.profile_root)
    for i in range(100):
        d = service.root / f"{i:032x}"
        d.mkdir(exist_ok=True)

    with patch("voicefont.experiment.MAX_EXPERIMENTS", 100):
        with pytest.raises(ExperimentError, match="limit reached"):
            service.start(session["id"], consent=True)


def test_work_save_failure_is_handled(tmp_path):
    """Lines 350-351: failed experiment save is logged but doesn't crash."""
    store = CalibrationStore(tmp_path / "profiles")
    session = store.create(name="Signal fixture", consent=True)
    for i in range(8):
        raw = _signal_wav(i)
        session = store.submit_take(session["id"], store.corpus["prompts"][i]["id"], f"take-{i}", raw)

    service = ExperimentService(store.profile_root)
    original_save = service._save
    call_count = [0]

    def failing_save(result):
        call_count[0] += 1
        if call_count[0] > 1:
            raise OSError("disk full")
        original_save(result)

    with patch.object(service, '_save', side_effect=failing_save):
        job = service.start(session["id"], consent=True)

    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        result = service.get(job["id"])
        if result["status"] not in ("queued", "running"):
            break
        time.sleep(0.03)

    assert result["status"] == "failed"


def _signal_wav(index):
    import io
    import wave

    import numpy as np
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
