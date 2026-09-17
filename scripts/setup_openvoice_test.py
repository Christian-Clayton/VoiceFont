"""Offline setup/launcher regression tests; no dependency installation."""

import importlib.util
import json
from pathlib import Path

import pytest


def module(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + ".py"))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def test_setup_rejects_corrupt_manifest_before_configuration(tmp_path):
    setup = module("setup_openvoice")
    (tmp_path / "runtime-manifest.json").write_text(
        json.dumps({"files": [{"path": "missing", "size": 1, "sha256": "0" * 64}]})
    )
    with pytest.raises((ValueError, OSError)):
        setup.verify_bundle(tmp_path)
    assert not (tmp_path / "config.json").exists()


def test_setup_rejects_manifest_traversal(tmp_path):
    setup = module("setup_openvoice")
    (tmp_path / "runtime-manifest.json").write_text(
        json.dumps({"files": [{"path": "../escape", "size": 1, "sha256": "0" * 64}]})
    )
    with pytest.raises(ValueError, match="manifest"):
        setup.verify_bundle(tmp_path)


def test_launcher_uses_offline_no_sync_and_loopback():
    launch = module("launch_voicefont")
    command = launch.server_command("uv.exe", 8765)
    assert command == [
        "uv.exe",
        "run",
        "--offline",
        "--no-sync",
        "python",
        "-m",
        "voicefont",
        "serve",
        "--host",
        "127.0.0.1",
        "--port",
        "8765",
    ]


def test_launcher_requires_voicefont_health():
    launch = module("launch_voicefont")
    assert not launch.valid_health({"status": "ok"})
    assert not launch.valid_health({"status": "ok", "local_only": False, "feature_version": "test"})
    assert launch.valid_health({"status": "ok", "local_only": True, "feature_version": "test"})
