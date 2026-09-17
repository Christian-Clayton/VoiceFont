"""Promote a verified local OpenVoice spike into a durable, hash-checked runtime.

No model/package downloads in this script. Copy only public assets, source and
cache resources; never copy a venv, user audio, generated embeddings or outputs.
Use --reuse-python explicitly, or recreate the isolated venv separately and pass
its executable. Serving never installs packages or fetches resources.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

REVISIONS = {
    "OpenVoice": "74a1d147b17a8c3092dd5430504bd83ef6c7eb23",
    "MeloTTS": "209145371cff8fc3bd60d7be902ea69cbdb7965a",
}
FOLDERS = ("OpenVoice", "MeloTTS", "assets", "hf-cache", "nltk-data")
DOCUMENTS = (
    "README.md",
    "requirements-frozen.txt",
    "download-manifest.json",
    "cached-resource-manifest.json",
    "dependency-license-metadata.json",
    "openvoice-spike.patch",
    "download_assets.py",
)


def digest(path):
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def provision(source: Path, destination: Path, python: Path, worker: Path):
    source, destination, python, worker = [
        p.resolve() for p in (source, destination, python, worker)
    ]
    if source == destination or destination.is_relative_to(source):
        raise ValueError("source and destination must be independent")
    version = subprocess.check_output(
        [str(python), "-c", "import sys; print('%s.%s'%sys.version_info[:2])"], text=True
    ).strip()
    if version != "3.10":
        raise ValueError("OpenVoice requires the isolated Python 3.10 environment")
    for name, expected in REVISIONS.items():
        revision = subprocess.check_output(
            ["git", "-C", str(source / name), "rev-parse", "HEAD"], text=True
        ).strip()
        if revision != expected:
            raise ValueError("unexpected upstream revision")
    # Verify recorded downloads/cache before promotion. Original absolute download
    # paths are rebased to the supplied source; portable cache paths are normalized.
    for entry in json.loads((source / "download-manifest.json").read_text()):
        relative = entry["path"].replace("\\", "/").split("/assets/", 1)[1]
        if digest(source / "assets" / relative) != entry["sha256"]:
            raise ValueError("asset hash mismatch")
    for entry in json.loads((source / "cached-resource-manifest.json").read_text()):
        if digest(source / entry["path"].replace("\\", "/")) != entry["sha256"]:
            raise ValueError("cached resource hash mismatch")
    destination.mkdir(parents=True, exist_ok=True)
    for name in FOLDERS:
        target = destination / name
        if target.exists():
            raise FileExistsError(f"Refusing to overwrite runtime folder: {name}")
        shutil.copytree(
            source / name,
            target,
            ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc", ".locks"),
        )
    provenance = destination / "provenance"
    provenance.mkdir(exist_ok=True)
    for name in DOCUMENTS:
        shutil.copy2(source / name, provenance / name)
    # This is the only upstream patch. Fail closed on an unknown source signature.
    api = destination / "OpenVoice/openvoice/api.py"
    original = "                device='cuda:0'):"
    patched = "                device='cuda:0', enable_watermark=True):"
    content = api.read_text(encoding="utf-8")
    if patched not in content:
        if content.count(original) != 1:
            raise ValueError("unknown OpenVoice constructor signature")
        api.write_text(content.replace(original, patched), encoding="utf-8")
    for name in ("torch-cache", "xdg-cache", "numba-cache", "mpl-cache"):
        (destination / name).mkdir(exist_ok=True)
    snapshots = {}
    for repo in sorted((destination / "hf-cache/hub").glob("models--*")):
        revision = (repo / "refs/main").read_text().strip()
        snapshot = repo / "snapshots" / revision
        if not snapshot.is_dir():
            raise ValueError("incomplete transformer snapshot")
        snapshots[repo.name.removeprefix("models--").replace("--", "/")] = snapshot.relative_to(
            destination
        ).as_posix()
    files = []
    for folder in FOLDERS:
        for path in sorted((destination / folder).rglob("*")):
            if path.is_file():
                files.append(
                    dict(
                        path=path.relative_to(destination).as_posix(),
                        size=path.stat().st_size,
                        sha256=digest(path),
                    )
                )
    (destination / "runtime-manifest.json").write_text(
        json.dumps(
            dict(
                schema_version=1,
                revisions=REVISIONS,
                tokenizer_snapshots=snapshots,
                files=files,
                patch="Constructor accepts enable_watermark=False; no model math change",
            ),
            indent=2,
        ),
        encoding="utf-8",
    )
    config = dict(
        schema_version=1,
        python=str(python),
        runtime_root=str(destination),
        worker=str(worker),
        device="cpu",
        timeout_seconds=180,
    )
    (destination / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    print(
        json.dumps(
            dict(
                config=str(destination / "config.json"),
                files=len(files),
                bytes=sum(f["size"] for f in files),
                python=str(python),
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument(
        "--destination",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data/openvoice-runtime",
    )
    parser.add_argument(
        "--reuse-python",
        type=Path,
        required=True,
        help="Explicit existing Python 3.10 executable; venv is not copied",
    )
    args = parser.parse_args()
    provision(
        args.source,
        args.destination,
        args.reuse_python,
        Path(__file__).with_name("openvoice_worker.py"),
    )
