"""Pinned offline ECAPA speaker embeddings. Neural computation is CUDA-only.

This is similarity retrieval, not authentication or proof of speaker identity.
Importing this module does not import torch or allocate GPU memory.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter

MODEL_REPO = "speechbrain/spkrec-ecapa-voxceleb"
MODEL_REVISION = "1464ca7a7269f8c2c07c94a63455216a38836dca"
MODEL_SHA256 = "0575cb64845e6b9a10db9bcb74d5ac32b326b8dc90352671d345e2ee3d0126a2"
EMBEDDING_VERSION = "ecapa-voxceleb-1464ca7-fbank80-sentence-l2-v1"
EMBEDDING_DIM = 192
MAX_SECONDS = 15


class EmbeddingUnavailable(RuntimeError):
    """Provisioned assets or CUDA runtime are unavailable; never fall back."""


def require_consent(consent: bool) -> None:
    if consent is not True:
        raise ValueError("explicit speaker embedding/search consent required")


def validate_embedding(vector, version: str) -> list[float]:
    """Require this exact encoder/preprocessing version and normalize safely."""
    if version != EMBEDDING_VERSION:
        raise ValueError("unsupported embedding version")
    if not isinstance(vector, (list, tuple)) or len(vector) != EMBEDDING_DIM:
        raise ValueError("embedding must contain 192 numbers")
    if any(type(x) not in (float, int) or not math.isfinite(x) for x in vector):
        raise ValueError("embedding must contain finite numbers, not booleans")
    norm = math.hypot(*vector)
    if not math.isfinite(norm) or norm < 1e-12:
        raise ValueError("embedding must have finite nonzero norm")
    return [float(x / norm) for x in vector]


def verify_model(model_dir: str | Path) -> Path:
    path = Path(model_dir) / "embedding_model.ckpt"
    if not path.is_file() or path.stat().st_size != 83316686:
        raise EmbeddingUnavailable("pinned ECAPA checkpoint missing or wrong size")
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if digest != MODEL_SHA256:
        raise EmbeddingUnavailable("ECAPA checkpoint hash mismatch")
    return path


@dataclass(frozen=True)
class EmbeddingResult:
    vector: list[float]
    version: str
    dimension: int
    audio_sha256: str
    device: str
    duration_seconds: float
    inference_ms: float
    peak_cuda_allocated_bytes: int

    def to_dict(self) -> dict:
        return asdict(self)


class CudaSpeakerEncoder:
    """One model per short-lived worker. Call close(), or use a context manager.

    No remote loader, YAML execution, model download, or CPU neural fallback.
    Signal decode/resampling is CPU preprocessing; Fbank and ECAPA run on CUDA.
    """

    def __init__(self, model_dir: str | Path, *, consent: bool):
        require_consent(consent)
        checkpoint = verify_model(model_dir)
        try:
            import torch
        except ImportError as exc:
            raise EmbeddingUnavailable("isolated CUDA embedding environment required") from exc
        if not torch.cuda.is_available():
            raise EmbeddingUnavailable("CUDA required; CPU neural fallback prohibited")
        from speechbrain.lobes.features import Fbank
        from speechbrain.lobes.models.ECAPA_TDNN import ECAPA_TDNN
        from speechbrain.processing.features import InputNormalization

        self.torch = torch
        self.features = Fbank(n_mels=80).to("cuda").eval()
        self.normalizer = InputNormalization(norm_type="sentence", std_norm=False).to("cuda")
        self.model = ECAPA_TDNN(
            input_size=80, channels=[1024, 1024, 1024, 1024, 3072],
            kernel_sizes=[5, 3, 3, 3, 1], dilations=[1, 2, 3, 4, 1],
            attention_channels=128, lin_neurons=192,
        )
        # Pinned upstream state dict, restricted unpickler; no remote code.
        self.model.load_state_dict(torch.load(checkpoint, map_location="cpu", weights_only=True))
        self.model.to("cuda").eval()
        assert next(self.model.parameters()).is_cuda

    def encode(self, source: str | Path | bytes, *, consent: bool) -> EmbeddingResult:
        require_consent(consent)
        if self.model is None:
            raise EmbeddingUnavailable("encoder is closed")
        from math import gcd

        import numpy as np
        from scipy.signal import resample_poly

        from voicefont.audio import read_audio

        audio = read_audio(source, max_duration=MAX_SECONDS, max_bytes=6 * 1024 * 1024)
        if audio.duration_seconds < 1.0:
            raise ValueError("speaker embedding requires at least one second of speech")
        divisor = gcd(audio.sample_rate, 16000)
        signal = resample_poly(audio.samples, 16000 // divisor, audio.sample_rate // divisor)
        torch = self.torch
        torch.cuda.reset_peak_memory_stats()
        torch.cuda.synchronize()
        started = perf_counter()
        with torch.inference_mode():
            waveform = torch.from_numpy(np.asarray(signal, dtype=np.float32)).unsqueeze(0).to("cuda")
            lengths = torch.ones(1, device="cuda")
            features = self.normalizer(self.features(waveform), lengths)
            embedded = self.model(features, lengths)
            if not embedded.is_cuda or not features.is_cuda:
                raise EmbeddingUnavailable("encoder computation escaped CUDA")
            vector = validate_embedding(embedded.flatten().cpu().tolist(), EMBEDDING_VERSION)
        torch.cuda.synchronize()
        return EmbeddingResult(
            vector, EMBEDDING_VERSION, EMBEDDING_DIM, audio.sha256, "cuda:0",
            audio.duration_seconds, (perf_counter() - started) * 1000,
            torch.cuda.max_memory_allocated(),
        )

    def close(self):
        self.model = self.features = self.normalizer = None
        self.torch.cuda.empty_cache()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
