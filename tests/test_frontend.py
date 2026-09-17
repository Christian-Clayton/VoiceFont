"""Serving boundary tests use an explicit minimal HTML fixture, not React build evidence."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from voicefont.frontend import mount_frontend


def test_unbuilt_frontend_has_actionable_response(tmp_path):
    app = FastAPI()
    mount_frontend(app, tmp_path)
    with TestClient(app) as client:
        response = client.get("/calibrate")
        assert response.status_code == 503
        assert "npm run build" in response.text


def test_built_frontend_serves_only_bundle_files(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text('<div id="root"></div>')
    (tmp_path / "assets/app-123.js").write_text("/* boundary fixture */")
    app = FastAPI()
    mount_frontend(app, tmp_path)
    with TestClient(app) as client:
        assert client.get("/").url.path == "/calibrate"
        assert client.get("/calibrate").text == '<div id="root"></div>'
        response = client.get("/assets/app-123.js")
        assert response.status_code == 200
        assert "javascript" in response.headers["content-type"]
