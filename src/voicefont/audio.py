"""Bounded PCM WAV ingestion and deterministic acoustic descriptors, not speaker embeddings."""

from __future__ import annotations

import hashlib
import io
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.signal import welch

MAX_FILE_BYTES = 50 * 1024 * 1024
MAX_DURATION_SECONDS = 180.0
FEATURE_VERSION = "acoustic-v1"
FEATURE_DIM = 16


class AudioError(ValueError):
    """Invalid or unsupported audio input."""


@dataclass(frozen=True)
class AudioData:
    """Mono float64 samples plus original PCM metadata and byte-exact provenance."""

    samples: np.ndarray
    sample_rate: int
    channels: int
    sample_width: int
    duration_seconds: float
    sha256: str
    raw_bytes: bytes


def read_audio(
    source: str | Path | bytes,
    *,
    max_bytes: int = MAX_FILE_BYTES,
    max_duration: float = MAX_DURATION_SECONDS,
) -> AudioData:
    """Read PCM 8/16/24/32-bit WAV; 1/2 channels, 8-96 kHz, 0.1-180 seconds.

    Reject RMS below 1e-4 or >1% samples at abs amplitude >=0.999.
    Validate channels before averaging, then reject cancelled/silent mono.
    """
    if isinstance(source, bytes):
        raw = source
    else:
        with Path(source).open("rb") as stream:
            raw = stream.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise AudioError("audio exceeds maximum file bytes")
    try:
        with wave.open(io.BytesIO(raw), "rb") as wav:
            channels, width, sr, frames, compression, _ = wav.getparams()
            if channels not in (1, 2) or width not in (1, 2, 3, 4) or compression != "NONE":
                raise AudioError("only mono/stereo integer PCM WAV is supported")
            if not 8000 <= sr <= 96000:
                raise AudioError("sample rate must be 8000-96000 Hz")
            duration = frames / sr
            if not 0.1 <= duration <= max_duration:
                raise AudioError("audio duration outside permitted range")
            pcm = wav.readframes(frames)
            if len(pcm) != frames * channels * width:
                raise AudioError("truncated PCM data")
    except (wave.Error, EOFError) as exc:
        raise AudioError("invalid PCM WAV") from exc
    if width == 1:
        samples = (np.frombuffer(pcm, dtype=np.uint8).astype(np.float64) - 128) / 128
    elif width == 3:
        octets = np.frombuffer(pcm, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        values = octets[:, 0] | (octets[:, 1] << 8) | (octets[:, 2] << 16)
        samples = ((values ^ 0x800000) - 0x800000).astype(np.float64) / 2**23
    else:
        samples = np.frombuffer(pcm, dtype=f"<i{width}").astype(np.float64) / 2 ** (8 * width - 1)
    clipping_threshold = min(0.999, 1 - 1 / 2 ** (width * 8 - 1))
    if np.mean(np.abs(samples) >= clipping_threshold) > 0.01:
        raise AudioError("audio has excessive clipping")
    mono = samples.reshape(-1, channels).mean(axis=1)
    if np.sqrt(np.mean((mono - mono.mean()) ** 2)) < 1e-4:
        raise AudioError("audio is silent or has no varying signal")
    mono.setflags(write=False)
    return AudioData(mono, sr, channels, width, duration, hashlib.sha256(raw).hexdigest(), raw)


def extract_features(audio: AudioData) -> np.ndarray:
    """16 unit-normalized values: 12 fixed spectral bands, RMS, ZCR, centroid, spread.

    Fixed bands span 0-4 kHz for all supported rates. These acoustic descriptors
    are recording-dependent and must not be used for speaker authentication.
    """
    signal = np.asarray(audio.samples, dtype=np.float64)
    if signal.ndim != 1 or signal.size < 2 or not np.isfinite(signal).all():
        raise AudioError("feature input must be finite nonempty mono audio")
    signal = signal - signal.mean()
    if np.linalg.norm(signal) < 1e-10:
        raise AudioError("feature input must be nonzero")
    frequencies, power = welch(signal, fs=audio.sample_rate, nperseg=min(2048, len(signal)))
    edges = np.linspace(0, 4000, 13)
    total = power.sum()
    bands = [
        power[(frequencies >= lo) & (frequencies < hi)].sum() / total
        for lo, hi in zip(edges[:-1], edges[1:], strict=True)
    ]
    centroid = float(np.dot(frequencies, power) / total)
    spread = float(np.sqrt(np.dot((frequencies - centroid) ** 2, power) / total))
    vector = np.array(
        bands
        + [
            float(np.sqrt(np.mean(signal**2))),
            float(np.mean(np.diff(np.signbit(signal)))),
            centroid / 48000,
            spread / 48000,
        ]
    )
    return vector / np.linalg.norm(vector)
