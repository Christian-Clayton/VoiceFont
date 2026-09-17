"""One genuine CPU synthesis process. Protocol: bounded UTF-8 JSON on stdin only.

Executed by the isolated Python 3.10 runtime, never imported by the core API.
No online fallback, logging, reference enrollment or fake-audio fallback.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import socket
import sys
from pathlib import Path


def forbidden(*args, **kwargs):
    raise RuntimeError("Network forbidden during offline synthesis")


def main():
    raw = sys.stdin.buffer.read(32769)
    if len(raw) > 32768:
        raise ValueError("request too large")
    request = json.loads(raw)
    root = Path(request["runtime_root"]).resolve()
    reference = Path(request["reference"]).resolve()
    output = Path(request["output"]).resolve()
    text = request["text"]
    speed = request["speed"]
    if not isinstance(text, str) or not text.strip() or len(text) > 1000:
        raise ValueError("invalid text")
    if (
        isinstance(speed, bool)
        or not isinstance(speed, (float, int))
        or not math.isfinite(speed)
        or not 0.75 <= speed <= 1.5
    ):
        raise ValueError("invalid speed")
    if reference.parent != output.parent or output.name != "speech.wav":
        raise ValueError("invalid job paths")
    # Set every offline guard before importing any third-party library.
    for key, value in {
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "HF_DATASETS_OFFLINE": "1",
        "HF_HUB_DISABLE_TELEMETRY": "1",
        "DO_NOT_TRACK": "1",
        "HF_HOME": str(root / "hf-cache"),
        "TORCH_HOME": str(root / "torch-cache"),
        "NLTK_DATA": str(root / "nltk-data"),
        "XDG_CACHE_HOME": str(root / "xdg-cache"),
        "NUMBA_CACHE_DIR": str(root / "numba-cache"),
        "MPLCONFIGDIR": str(root / "mpl-cache"),
        "TEMP": str(output.parent),
        "TMP": str(output.parent),
    }.items():
        os.environ[key] = value
    socket.socket.connect = forbidden
    socket.socket.connect_ex = forbidden
    socket.create_connection = forbidden
    socket.getaddrinfo = forbidden
    sys.path[:0] = [str(root / "OpenVoice"), str(root / "MeloTTS")]

    manifest = json.loads((root / "runtime-manifest.json").read_text(encoding="utf-8"))
    # Check hashes before torch/pickle deserialization. Manifest is owner-trusted.
    for entry in manifest["files"]:
        path = root / entry["path"]
        if not path.resolve().is_relative_to(root):
            raise ValueError("invalid manifest")
        with path.open("rb") as stream:
            digest = (
                hashlib.file_digest(stream, "sha256").hexdigest()
                if hasattr(hashlib, "file_digest")
                else None
            )
            if digest is None:  # Python 3.10
                h = hashlib.sha256()
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    h.update(chunk)
                digest = h.hexdigest()
        if digest != entry["sha256"]:
            raise ValueError("runtime integrity mismatch")

    import numpy as np
    import torch
    import transformers

    # Upstream Melo uses model IDs at import time. Resolve only exact cached
    # snapshots pinned during explicit provisioning, never 'main' or remote URLs.
    for auto_class in (transformers.AutoTokenizer, transformers.AutoModelForMaskedLM):
        original = auto_class.from_pretrained

        def pinned(identifier, *args, _original=original, **kwargs):
            if identifier not in manifest["tokenizer_snapshots"]:
                raise ValueError("unprovisioned transformer resource")
            kwargs.pop("revision", None)
            kwargs["local_files_only"] = True
            return _original(
                str(root / manifest["tokenizer_snapshots"][identifier]), *args, **kwargs
            )

        auto_class.from_pretrained = staticmethod(pinned)

    torch.set_num_threads(4)
    torch.manual_seed(42)
    np.random.seed(42)
    from melo.api import TTS
    from openvoice.api import ToneColorConverter

    checkpoint = root / "assets/OpenVoiceV2/converter"
    converter = ToneColorConverter(
        str(checkpoint / "config.json"), device="cpu", enable_watermark=False
    )
    converter.load_ckpt(str(checkpoint / "checkpoint.pth"))
    if converter.version != "v2":
        raise ValueError("unexpected converter")
    target = converter.extract_se(str(reference))
    if not torch.isfinite(target).all():
        raise ValueError("invalid reference embedding")
    assets = root / "assets/MeloTTS-English-v3"
    model = TTS(
        language="EN_NEWEST",
        device="cpu",
        config_path=str(assets / "config.json"),
        ckpt_path=str(assets / "checkpoint.pth"),
    )
    base = output.parent / "melo-base.wav"
    model.tts_to_file(text, 0, str(base), speed=speed)
    source = torch.load(
        root / "assets/OpenVoiceV2/base_speakers/ses/en-newest.pth", map_location="cpu"
    )
    converter.convert(
        str(base), src_se=source, tgt_se=target, output_path=str(output), message="Synthetic"
    )


if __name__ == "__main__":
    # Upstream libraries print private text. Suppress at the OS descriptor boundary,
    # including imports, native libraries and all exceptions. Exit code is the protocol.
    null = os.open(os.devnull, os.O_WRONLY)
    os.dup2(null, 1)
    os.dup2(null, 2)
    os.close(null)
    try:
        main()
    except Exception:
        sys.exit(1)
