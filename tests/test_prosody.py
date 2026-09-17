"""Prosodic contour extraction tests: generated signals, never voice claims."""

import numpy as np
import pytest

from voicefont.audio import read_audio
from voicefont.prosody import PROSODY_VERSION, contour


def tone(rate=16000, seconds=1.0, frequency=180, amplitude=0.2):
    n = int(rate * seconds)
    t = np.arange(n) / rate
    pcm = (amplitude * np.sin(2 * np.pi * frequency * t) * 32767).astype("<i2")
    import io
    import wave

    stream = io.BytesIO()
    with wave.open(stream, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(pcm.tobytes())
    return stream.getvalue()


def rising_amplitude(rate=16000, seconds=1.0):
    n = int(rate * seconds)
    t = np.arange(n) / rate
    envelope = np.linspace(0.02, 0.4, n)
    pcm = (envelope * np.sin(2 * np.pi * 180 * t) * 32767).astype("<i2")
    import io
    import wave

    stream = io.BytesIO()
    with wave.open(stream, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(pcm.tobytes())
    return stream.getvalue()


def test_version_is_declared():
    assert PROSODY_VERSION == "prosody-v1"


def test_contour_shape_and_bounded_values():
    result = contour(read_audio(tone()))
    assert result["frame_seconds"] == pytest.approx(0.032)
    assert len(result["pitch_hz"]) == len(result["energy_rms"]) == len(result["centroid_hz"])
    assert all(np.isfinite(result["pitch_hz"]))
    assert all(np.isfinite(result["energy_rms"]))
    assert all(0 < value < 96000 for value in result["pitch_hz"])


def test_louder_half_has_higher_energy_median():
    quiet = contour(read_audio(tone(amplitude=0.05)))
    loud = contour(read_audio(tone(amplitude=0.4)))
    assert np.median(loud["energy_rms"]) > np.median(quiet["energy_rms"])


def test_rising_envelope_energy_trend_is_positive():
    result = contour(read_audio(rising_amplitude()))
    first, last = result["energy_rms"][0], result["energy_rms"][-1]
    assert last > first * 3


def test_higher_pitch_tone_detects_higher_median_f0():
    low = contour(read_audio(tone(frequency=120)))
    high = contour(read_audio(tone(frequency=280)))
    assert np.median(high["pitch_hz"]) > np.median(low["pitch_hz"])


def test_silent_frames_are_masked_in_mixed_recording():
    rate = 16000
    n = rate
    t = np.arange(n) / rate
    envelope = np.where(t < 0.5, 0.0005, 0.3)
    pcm = (envelope * np.sin(2 * np.pi * 180 * t) * 32767).astype("<i2")
    import io
    import wave

    stream = io.BytesIO()
    with wave.open(stream, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(pcm.tobytes())
    result = contour(read_audio(stream.getvalue()))
    assert 0.0 < result["voiced_fraction"] < 0.7
    assert len(result["pitch_hz"]) >= 5
