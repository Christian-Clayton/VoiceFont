"""Recreate the Windows CPU inference environment; verify offline before enabling it.

Only this explicit setup step may download packages. Requires an already promoted
runtime bundle (see provision_openvoice.py). Never copies a virtual environment.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_SHA256 = "d0f5806f6e034e660c46a0b2fe4c597f0a1670859743c14e27a8823a7d169263"


def sha256(path):
    with path.open("rb") as stream:
        result = hashlib.sha256()
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
        return result.hexdigest()


def verify_bundle(root):
    manifest = json.loads((root / "runtime-manifest.json").read_text(encoding="utf-8"))
    if not manifest.get("files"):
        raise ValueError("empty runtime manifest")
    for item in manifest["files"]:
        path = (root / item["path"]).resolve()
        if not path.is_relative_to(root.resolve()):
            raise ValueError("invalid runtime manifest path")
        if path.stat().st_size != item["size"] or sha256(path) != item["sha256"]:
            raise ValueError("runtime manifest integrity mismatch")
    return len(manifest["files"])


def verify_inference(root, python):
    fixture = root / "OpenVoice/resources/example_reference.mp3"
    if sha256(fixture) != FIXTURE_SHA256:
        raise ValueError("unexpected official technical fixture")
    evidence = root / "verification"
    evidence.mkdir(exist_ok=True)
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="setup-fixture-", dir=evidence) as directory:
        job = Path(directory)
        reference = job / "reference.mp3"
        shutil.copyfile(fixture, reference)
        output = job / "speech.wav"
        request = dict(
            runtime_root=str(root),
            reference=str(reference),
            output=str(output),
            text="This is a local speech test. No cloud service is used.",
            speed=1.0,
        )
        subprocess.run(
            [str(python), str(ROOT / "scripts/openvoice_worker.py")],
            input=json.dumps(request).encode(),
            check=True,
            timeout=180,
        )
        with wave.open(str(output), "rb") as audio:
            rate = audio.getframerate()
            duration = audio.getnframes() / rate
            if rate != 22050 or duration <= 1 or audio.getnchannels() != 1:
                raise ValueError("unexpected neural audio format")
        digest = sha256(output)
        # The pinned seeded fixture also proves non-silent neural output parity.
        expected = "31deaac0f90a71476002df1ddd99b147aff94dd3548dd2ec04a82b9894c3ae02"
        if digest != expected:
            raise ValueError("technical fixture differs from verified baseline")
        shutil.copyfile(output, evidence / "durable-technical-fixture.wav")
    result = dict(
        python=str(python),
        sha256=digest,
        duration_seconds=duration,
        sample_rate=rate,
        elapsed_seconds=time.monotonic() - started,
        technical_fixture_only=True,
        offline_python_network_blocked=True,
        speaker_release_independently_verified=False,
    )
    (evidence / "durable-result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--python", default="3.10", help="Installed Python 3.10 executable or version"
    )
    parser.add_argument("--offline", action="store_true", help="Use only the populated uv cache")
    parser.add_argument(
        "--verify-only", action="store_true", help="Skip package setup; test and configure"
    )
    args = parser.parse_args()
    runtime = ROOT / "data/openvoice-runtime"
    count = verify_bundle(runtime)
    python = ROOT / ".venv-openvoice/Scripts/python.exe"
    uv = shutil.which("uv")
    if not args.verify_only:
        if not uv:
            raise ValueError("Install uv first; see docs/local-setup.md")
        flags = ["--offline"] if args.offline else []
        if not python.exists():
            subprocess.run(
                [
                    uv,
                    "venv",
                    "--no-project",
                    "--python",
                    args.python,
                    *flags,
                    str(python.parents[1]),
                ],
                check=True,
                timeout=300,
            )
        subprocess.run(
            [
                uv,
                "pip",
                "sync",
                *flags,
                "--python",
                str(python),
                str(ROOT / "requirements-openvoice.txt"),
            ],
            check=True,
            timeout=900,
        )
        subprocess.run([uv, "pip", "check", "--python", str(python)], check=True, timeout=60)
    version = subprocess.check_output(
        [str(python), "-c", "import sys; print(sys.version_info[:2])"], text=True
    ).strip()
    if version != "(3, 10)":
        raise ValueError("Inference environment must be Python 3.10")
    result = verify_inference(runtime, python)
    config = dict(
        schema_version=1,
        python=str(python),
        runtime_root=str(runtime),
        worker=str(ROOT / "scripts/openvoice_worker.py"),
        device="cpu",
        timeout_seconds=180,
    )
    pending = runtime / "config.pending.json"
    pending.write_text(json.dumps(config, indent=2), encoding="utf-8")
    pending.replace(runtime / "config.json")
    print(json.dumps(dict(configured=True, verified_files=count, **result), indent=2))


if __name__ == "__main__":
    main()
