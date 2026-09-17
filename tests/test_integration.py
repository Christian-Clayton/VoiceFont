"""Integration of calibration and synthesis routers with the local app."""

from fastapi.testclient import TestClient

from voicefont.api import create_app


def test_routers_are_mounted_with_browser_page_and_assets(tmp_path, monkeypatch):
    monkeypatch.setenv("VOICEFONT_OPENVOICE_CONFIG", str(tmp_path / "missing-config.json"))
    client = TestClient(create_app(tmp_path))
    for path in ("/calibrate", "/calibration/corpus", "/calibration-assets/app.js"):
        assert client.get(path).status_code == 200, path
    capabilities = client.get("/synthesis/capabilities").json()
    assert capabilities["available"] is False
    assert capabilities["backend"] == "openvoice-v2"
    assert capabilities["device"] == "cpu"
    assert (
        "not provisioned" in capabilities["message"] or "not configured" in capabilities["message"]
    )


def test_browser_same_origin_is_allowed_but_foreign_origin_rejected(tmp_path):
    client = TestClient(create_app(tmp_path))
    assert client.get("/health", headers={"origin": "http://testserver"}).status_code == 200
    assert client.get("/health", headers={"origin": "http://testserver:9000"}).status_code == 403
    assert client.get("/health", headers={"origin": "null"}).status_code == 403
    assert client.get("/health", headers={"origin": "https://evil.example"}).status_code == 403


def test_speak_still_reports_unavailable_without_backend(tmp_path, monkeypatch):
    monkeypatch.setenv("VOICEFONT_OPENVOICE_CONFIG", str(tmp_path / "absent.json"))
    with TestClient(create_app(tmp_path)) as client:
        response = client.post("/speak", json={"voice_id": "test", "text": "Hello"})
        assert response.status_code == 503


def test_speak_reuses_jobs_service_and_validates_body(tmp_path, monkeypatch):
    app = create_app(tmp_path)
    calls = []

    def submit(**body):
        calls.append(body)
        return {"id": "boundary-test", "status": "queued"}

    with TestClient(app) as client:
        monkeypatch.setattr(app.state.synthesis_service, "submit", submit)
        body = {"voice_id": "test", "text": "Hello"}
        assert client.post("/speak", json=body).status_code == 202
        assert client.post("/synthesis/jobs", json=body).status_code == 202
        assert calls[0] == calls[1]
        assert client.post("/speak", json={**body, "reference": "bad"}).status_code == 422
    assert app.state.synthesis_service.closed


def test_session_corpus_route_exposes_saved_snapshot(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        corpus = client.get("/calibration/corpus").json()
        session = client.post(
            "/calibration/sessions", json={"name": "Snapshot", "consent": True, "mode": "full"}
        ).json()
        response = client.get(f"/calibration/sessions/{session['id']}/corpus")
        assert response.status_code == 200
        assert response.json() == corpus


def test_experiment_router_is_mounted(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        response = client.get("/experiments/capabilities")
        assert response.status_code == 200
        assert isinstance(response.json(), dict)


def test_internal_asset_sources_not_served(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        assert client.get("/calibration-assets/build_corpus.py").status_code == 404
        assert client.get("/calibration-assets/recorder.test.cjs").status_code == 404
        assert client.get("/calibration-assets/styles.css").status_code == 200
