"""Provision pinned local tools without modifying PATH or global kubeconfig."""

import hashlib
import json
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "data/cluster-tools"


def fetch(url, path):
    with urllib.request.urlopen(url, timeout=90) as response:
        path.write_bytes(response.read())


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    version = "v5.8.3"
    base = f"https://github.com/k3d-io/k3d/releases/download/{version}"
    binary = ROOT / "k3d.exe"
    fetch(base + "/k3d-windows-amd64.exe", binary)
    sums = ROOT / "k3d-checksums.txt"
    fetch(base + "/checksums.txt", sums)
    digest = hashlib.sha256(binary.read_bytes()).hexdigest()
    if not any(digest in line and "k3d-windows-amd64.exe" in line
               for line in sums.read_text().splitlines()):
        raise RuntimeError("k3d checksum mismatch")
    tf = "1.12.2"
    base = f"https://releases.hashicorp.com/terraform/{tf}"
    archive = ROOT / f"terraform_{tf}_windows_amd64.zip"
    fetch(base + "/" + archive.name, archive)
    sums = ROOT / "terraform-checksums.txt"
    fetch(base + f"/terraform_{tf}_SHA256SUMS", sums)
    tf_digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    if not any(tf_digest in line and archive.name in line
               for line in sums.read_text().splitlines()):
        raise RuntimeError("Terraform checksum mismatch")
    with zipfile.ZipFile(archive) as bundle:
        (ROOT / "terraform.exe").write_bytes(bundle.read("terraform.exe"))
    print(json.dumps({"k3d": version, "k3d_sha256": digest,
                      "terraform": tf, "terraform_zip_sha256": tf_digest}))


if __name__ == "__main__":
    main()
