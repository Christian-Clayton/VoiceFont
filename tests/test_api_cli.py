import json

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from voicefont.api import create_app
from voicefont.cli import app


def test_api_enroll_search_inspect_and_unavailable_synthesis(signal_wav, tmp_path):
    client = TestClient(create_app(tmp_path))
    assert client.get("/health").json() == {
        "status": "ok",
        "local_only": True,
        "feature_version": "acoustic-v1",
        "synthesis_available": False,
    }
    assert client.get("/profiles").json() == []
    params = {"voice_id": "signal", "name": "Signal fixture", "consent": "true"}
    response = client.post(
        "/profiles", params=params, content=signal_wav(), headers={"content-type": "audio/wav"}
    )
    assert response.status_code == 201
    assert response.json()["consent"]["asserted"] is True
    assert client.get("/profiles/signal").json() == response.json()
    assert len(client.get("/profiles").json()) == 1
    assert (
        client.post(
            "/profiles", params=params, content=signal_wav(), headers={"content-type": "audio/wav"}
        ).status_code
        == 409
    )
    matches = client.post(
        "/search", content=signal_wav(), headers={"content-type": "audio/wav"}
    ).json()
    assert matches[0]["voice_id"] == "signal"
    assert matches[0]["score"] == pytest.approx(1)
    assert client.get("/profiles/signal/similar").json() == matches
    assert client.post("/speak", json={"voice_id": "signal", "text": "Test"}).status_code == 503
    assert client.get("/profiles/missing").status_code == 404


@pytest.mark.parametrize(
    "params",
    [
        dict(voice_id="signal", name="Signal"),
        dict(voice_id="signal", name="Signal", consent="false"),
        dict(voice_id="../escape", name="Signal", consent="true"),
    ],
)
def test_api_consent_and_id_boundaries(signal_wav, tmp_path, params):
    client = TestClient(create_app(tmp_path))
    assert (
        client.post(
            "/profiles", params=params, content=signal_wav(), headers={"content-type": "audio/wav"}
        ).status_code
        == 422
    )
    assert client.get("/profiles").json() == []


def test_api_rejects_urls_large_bodies_foreign_origins_and_hosts(tmp_path):
    client = TestClient(create_app(tmp_path, max_upload_bytes=100))
    assert client.post("/search", json={"reference": "http://example.com/a.wav"}).status_code == 415
    assert (
        client.post(
            "/search", content=b"x" * 101, headers={"content-type": "audio/wav"}
        ).status_code
        == 413
    )
    assert (
        client.post("/search", content=b"x", headers={"content-type": "audio/wav"}).status_code
        == 422
    )
    assert client.get("/health", headers={"origin": "https://example.com"}).status_code == 403
    assert client.get("/health", headers={"host": "evil.example"}).status_code == 400
    assert client.get("/health").headers["x-content-type-options"] == "nosniff"
    assert (
        client.post(
            "/search?top_k=0", content=b"x", headers={"content-type": "audio/wav"}
        ).status_code
        == 422
    )


def test_cli_signal_fixture_roundtrip_and_no_consent(signal_wav, tmp_path):
    source = tmp_path / "synthetic-signal.wav"
    source.write_bytes(signal_wav())
    runner = CliRunner()
    root = ["--root", str(tmp_path / "registry")]
    command = ["enroll", "--reference", str(source), "--voice-id", "signal", "--name", "Signal"]
    denied = runner.invoke(app, command + root)
    assert denied.exit_code != 0
    assert "consent" in denied.output.lower()
    enrolled = runner.invoke(app, command + root + ["--consent"])
    assert enrolled.exit_code == 0, enrolled.output
    assert json.loads(enrolled.output)["voice_id"] == "signal"
    matches = runner.invoke(app, ["search", "--reference", str(source)] + root)
    assert matches.exit_code == 0, matches.output
    assert json.loads(matches.output)[0]["voice_id"] == "signal"
    inspected = runner.invoke(app, ["inspect", "--voice-id", "signal"] + root)
    assert json.loads(inspected.output)["schema_version"] == "1.0.0"
    listed = runner.invoke(app, ["list"] + root)
    assert len(json.loads(listed.output)) == 1
    missing = runner.invoke(app, ["inspect", "--voice-id", "missing"] + root)
    assert missing.exit_code == 1
    assert "Traceback" not in missing.output


def test_serve_default_is_loopback_and_nonlocal_binding_rejected(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr("uvicorn.run", lambda *args, **kwargs: calls.append(kwargs))
    result = CliRunner().invoke(app, ["serve", "--root", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert calls[0]["host"] == "127.0.0.1"
    assert CliRunner().invoke(app, ["serve", "--host", "0.0.0.0"]).exit_code != 0


def test_serve_disables_sensitive_access_logs(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr("uvicorn.run", lambda *args, **kwargs: calls.append(kwargs))
    result = CliRunner().invoke(app, ["serve", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert calls[0].get("access_log") is False


def test_serve_rejects_unsupported_ipv6_binding(monkeypatch):
    calls = []
    monkeypatch.setattr("uvicorn.run", lambda *args, **kwargs: calls.append(kwargs))
    result = CliRunner().invoke(app, ["serve", "--host", "::1"])
    assert result.exit_code != 0
    assert not calls
