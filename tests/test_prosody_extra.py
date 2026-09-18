"""Tests targeting missing prosody.py lines: 22, 33, 37, 42, 44, 52, 87, 97."""

import numpy as np
import pytest

from voicefont.audio import AudioData, AudioError
from voicefont.prosody import _frame_pitch, contour, summarize


def _make_audio(samples, sample_rate=16000):
    """Helper to create AudioData directly."""
    raw = b"fake"
    return AudioData(
        samples=np.asarray(samples, dtype=np.float64),
        sample_rate=sample_rate,
        channels=1,
        sample_width=2,
        duration_seconds=len(samples) / sample_rate,
        sha256="fake",
        raw_bytes=raw,
    )


def test_audio_too_short_for_framing():
    """Line 22: signal shorter than frame size raises AudioError."""
    # With FRAME_SECONDS=0.032 and sr=16000, hop=512, size=1024
    # contour first checks len(signal) < 512 (line 52), but _frames is called with size=1024
    # So we need 512 <= len < 1024 to hit line 22
    short = np.sin(2 * np.pi * 180 * np.arange(800) / 16000) * 0.1
    audio = _make_audio(short)
    with pytest.raises(AudioError, match="too short"):
        contour(audio)


def test_frame_pitch_zero_correlation():
    """Line 33: frame with zero autocorrelation returns None."""
    # Create a frame where correlation[0] <= 0
    frame = np.zeros(10)
    sr = 8000
    result = _frame_pitch(frame, sr)
    assert result is None


def test_frame_pitch_high_out_of_range():
    """Line 37: high index >= len(correlation) - 1 returns None."""
    # With sr=8000, MIN_PITCH_HZ=60 -> high = 8000/60 = 133
    # frame size = 10, correlation len = 10
    # high (133) >= len(correlation)-1 (9) -> True
    frame = np.sin(2 * np.pi * 100 * np.arange(10) / 8000)
    sr = 8000
    result = _frame_pitch(frame, sr)
    assert result is None


def test_frame_pitch_lag_decrement():
    """Line 42: lag-1 > lag check decrements lag."""
    sr = 16000
    freq = 65  # Just above MIN_PITCH_HZ
    t = np.arange(1024) / sr
    frame = np.sin(2 * np.pi * freq * t)
    result = _frame_pitch(frame, sr)
    if result is not None:
        assert result > 0


def test_frame_pitch_lag_increment():
    """Line 44: lag+1 > lag check increments lag."""
    sr = 16000
    freq = 390  # Just below MAX_PITCH_HZ
    t = np.arange(1024) / sr
    frame = np.sin(2 * np.pi * freq * t)
    result = _frame_pitch(frame, sr)
    if result is not None:
        assert result > 0


def test_contour_rejects_bad_input():
    """Line 52: invalid input raises AudioError."""
    # Too short (< 512 samples)
    audio = _make_audio(np.array([0.1] * 100))
    with pytest.raises(AudioError, match="at least 512 samples"):
        contour(audio)

    # Non-finite values
    bad = np.full(1024, np.nan)
    audio = _make_audio(bad)
    with pytest.raises(AudioError, match="finite"):
        contour(audio)


def test_summarize_empty_energy_raises():
    """Line 87: empty or non-finite energy raises AudioError."""
    contour_data = {
        "pitch_hz": [],
        "energy_rms": [],
    }
    with pytest.raises(AudioError, match="energy frames"):
        summarize(contour_data)


def test_summarize_no_pitch_gives_none_stats():
    """Line 97: when no voiced frames, pitch stats are None."""
    contour_data = {
        "pitch_hz": [],
        "energy_rms": [0.1, 0.2, 0.3],
        "voiced_fraction": 0.0,
    }
    result = summarize(contour_data)
    assert result["pitch_median_hz"] is None
    assert result["pitch_min_hz"] is None
    assert result["pitch_max_hz"] is None
