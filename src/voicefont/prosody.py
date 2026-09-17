"""Deterministic prosodic contours: pitch, energy and brightness over time.

Versioned like acoustic-v1. These are recording descriptors, not speaker
verification data and not a claim of capturing expressive identity.
"""

from __future__ import annotations

import numpy as np

from .audio import AudioData, AudioError

PROSODY_VERSION = "prosody-v1"
FRAME_SECONDS = 0.032
MIN_PITCH_HZ = 60.0
MAX_PITCH_HZ = 400.0


def _frames(signal: np.ndarray, hop: int, size: int) -> np.ndarray:
    count = max(0, 1 + (len(signal) - size) // hop)
    if count < 1:
        raise AudioError("audio too short for prosodic framing")
    strides = (signal.strides[0] * hop, signal.strides[0])
    return np.lib.stride_tricks.as_strided(
        signal, shape=(count, size), strides=strides, writeable=False
    )


def _frame_pitch(frame: np.ndarray, sample_rate: int) -> float | None:
    window = frame - frame.mean()
    correlation = np.correlate(window, window, mode="full")[len(window) - 1 :]
    if correlation[0] <= 0:
        return None
    correlation /= correlation[0]
    low, high = int(sample_rate / MAX_PITCH_HZ), int(sample_rate / MIN_PITCH_HZ)
    if high >= len(correlation) - 1:
        return None
    lag = int(np.argmax(correlation[low : high + 1])) + low
    if correlation[lag] < 0.5:
        return None
    if lag > 1 and correlation[lag - 1] > correlation[lag]:
        lag -= 1
    if lag < len(correlation) - 2 and correlation[lag + 1] > correlation[lag]:
        lag += 1
    return float(sample_rate / lag)


def contour(audio: AudioData) -> dict:
    """Return per-frame pitch/energy/centroid plus bounded summary scalars."""
    signal = np.asarray(audio.samples, dtype=np.float64)
    if signal.ndim != 1 or len(signal) < 512 or not np.isfinite(signal).all():
        raise AudioError("prosody input must be finite mono audio of at least 512 samples")
    signal = signal - signal.mean()
    hop = max(1, int(FRAME_SECONDS * audio.sample_rate))
    size = 2 * hop
    windows = _frames(signal, hop, size) * np.hanning(size)
    energy = np.sqrt(np.mean(windows**2, axis=1))
    spectra = np.abs(np.fft.rfft(windows, axis=1))
    frequencies = np.fft.rfftfreq(size, 1 / audio.sample_rate)
    totals = spectra.sum(axis=1)
    totals[totals == 0] = 1.0
    centroid = (spectra * frequencies).sum(axis=1) / totals
    # Relative voicing mask: frames below 5% of the 90th-percentile energy are
    # unvoiced regardless of absolute gain, so quiet recordings still work.
    reference = np.percentile(energy, 90) or 1.0
    pitch = [
        None if value < 0.05 * reference else _frame_pitch(windows[index], audio.sample_rate)
        for index, value in enumerate(energy)
    ]
    voiced = [value for value in pitch if value is not None]
    total = len(energy)
    return {
        "version": PROSODY_VERSION,
        "frame_seconds": hop / audio.sample_rate,
        "pitch_hz": [round(value, 2) for value in voiced],
        "energy_rms": [round(float(value), 6) for value in energy],
        "centroid_hz": [round(float(value), 2) for value in centroid],
        "voiced_fraction": round(len(voiced) / total, 4),
    }


def summarize(contour_data: dict) -> dict:
    """Bounded numeric summary for storage next to profile descriptors."""
    pitch = np.asarray(contour_data.get("pitch_hz", []), dtype=np.float64)
    energy = np.asarray(contour_data.get("energy_rms", []), dtype=np.float64)
    if energy.size == 0 or not np.isfinite(energy).all():
        raise AudioError("prosody summary requires finite energy frames")
    trend = float(np.polyfit(np.arange(energy.size), energy, 1)[0]) if energy.size > 1 else 0.0
    scale = float(np.max(energy)) or 1.0
    if pitch.size:
        pitch_stats = {
            "pitch_median_hz": round(float(np.median(pitch)), 2),
            "pitch_min_hz": round(float(pitch.min()), 2),
            "pitch_max_hz": round(float(pitch.max()), 2),
        }
    else:
        pitch_stats = {"pitch_median_hz": None, "pitch_min_hz": None, "pitch_max_hz": None}
    return {
        "version": PROSODY_VERSION,
        **pitch_stats,
        "energy_min": round(float(energy.min()), 6),
        "energy_max": round(float(energy.max()), 6),
        "energy_trend_per_frame": round(trend / scale, 6),
        "voiced_fraction": contour_data.get("voiced_fraction", 0.0),
    }
