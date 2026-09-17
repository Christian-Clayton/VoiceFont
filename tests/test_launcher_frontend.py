"""Launcher refuses an unavailable UI, even when API health succeeds."""

import importlib.util
from pathlib import Path

import pytest


def load_launcher():
    path = Path(__file__).resolve().parents[1] / "scripts/launch_voicefont.py"
    spec = importlib.util.spec_from_file_location("launch_frontend_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_launcher_rejects_missing_react_bundle(tmp_path):
    launcher = load_launcher()
    with pytest.raises(RuntimeError, match="React frontend"):
        launcher.require_frontend(tmp_path)


def test_launcher_rejects_missing_compiled_assets(tmp_path):
    launcher = load_launcher()
    bundle = tmp_path / "frontend/dist"
    bundle.mkdir(parents=True)
    (bundle / "index.html").write_text('<div id="root"></div>')
    with pytest.raises(RuntimeError, match="React frontend"):
        launcher.require_frontend(tmp_path)


def test_launcher_accepts_local_compiled_bundle(tmp_path):
    launcher = load_launcher()
    bundle = tmp_path / "frontend/dist"
    (bundle / "assets").mkdir(parents=True)
    (bundle / "index.html").write_text('<script src="/assets/index.js"></script>')
    (bundle / "assets/index.js").write_text("// generated bundle fixture")
    launcher.require_frontend(tmp_path)
