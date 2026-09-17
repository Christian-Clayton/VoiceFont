"""Generated signals test storage mechanics, never human voice quality."""

import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from voicefont.audio import AudioError
from voicefont.calibration import CalibrationError, CalibrationStore


def test_takes_idempotency_rerecord_selection_and_exact_audio(tmp_path, corpus, signal_wav):
    store = CalibrationStore(tmp_path / "profiles", corpus=corpus)
    sid = store.create(name="Mine", consent=True, mode="adaptive")["id"]
    raw = signal_wav()
    first = store.submit_take(sid, "p1", "take-1", raw)
    assert first["next_prompt_id"] == "p3"
    assert store.submit_take(sid, "p1", "take-1", raw) == first
    with pytest.raises(CalibrationError, match="conflict"):
        store.submit_take(sid, "p1", "take-1", signal_wav(660))
    with pytest.raises(CalibrationError, match="conflict"):
        store.submit_take(sid, "p2", "take-1", raw)
    with pytest.raises(AudioError):
        store.submit_take(sid, "p1", "bad-take", signal_wav(amplitude=0))
    assert store.get(sid) == first
    second = store.submit_take(sid, "p1", "take-2", signal_wav(660))
    assert second["accepted"] == {"p1": "take-2"}
    assert len(second["takes"]) == 2
    assert set(second["takes"][0]["quality"]) == {"rms", "peak", "clipping_fraction"}
    assert store.audio(sid, "take-1") == raw
    assert store.select(sid, "p1", "take-1")["accepted"] == {"p1": "take-1"}
    with pytest.raises(CalibrationError):
        store.select(sid, "p2", "take-1")
    with pytest.raises(FileNotFoundError):
        store.audio(sid, "not-owned")
    assert CalibrationStore(tmp_path / "profiles", corpus=corpus).audio(sid, "take-1") == raw


def test_concurrent_submissions_do_not_lose_takes(tmp_path, corpus, signal_wav):
    store = CalibrationStore(tmp_path / "profiles", corpus=corpus)
    sid = store.create(name="Mine", consent=True)["id"]
    raw = signal_wav()

    def submit(n):
        other = CalibrationStore(tmp_path / "profiles", corpus=corpus)
        return other.submit_take(sid, "p1", f"take-{n}", raw)

    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(submit, range(12)))
    assert len(store.get(sid)["takes"]) == 12


def test_snapshot_corpus_and_skip_then_record(tmp_path, corpus, signal_wav):
    store = CalibrationStore(tmp_path / "profiles", corpus=corpus)
    sid = store.create(name="Mine", consent=True)["id"]
    store.skip(sid, "p1")
    corpus["prompts"] = []
    other = CalibrationStore(tmp_path / "profiles", corpus=corpus)
    session = other.submit_take(sid, "p1", "take-1", signal_wav())
    assert session["skipped"] == []
    assert session["coverage"]["total"] == 4


def test_tampered_raw_fails_integrity(tmp_path, corpus, signal_wav):
    store = CalibrationStore(tmp_path / "profiles", corpus=corpus)
    sid = store.create(name="Mine", consent=True)["id"]
    store.submit_take(sid, "p1", "take-1", signal_wav())
    (tmp_path / "calibration" / sid / "takes" / "take-1.wav").write_bytes(signal_wav(880))
    with pytest.raises(CalibrationError, match="integrity"):
        store.audio(sid, "take-1")


def test_orphan_take_is_never_overwritten(tmp_path, corpus, signal_wav):
    store = CalibrationStore(tmp_path / "profiles", corpus=corpus)
    sid = store.create(name="Mine", consent=True)["id"]
    path = tmp_path / "calibration" / sid / "takes" / "take-1.wav"
    path.write_bytes(signal_wav())
    with pytest.raises(CalibrationError, match="conflict"):
        store.submit_take(sid, "p1", "take-1", signal_wav(660))
    assert path.read_bytes() == signal_wav()
    assert len(store.submit_take(sid, "p1", "take-1", signal_wav())["takes"]) == 1


@pytest.mark.parametrize(
    "field,value", [("schema_version", "future"), ("consent", {"asserted": False})]
)
def test_stored_schema_and_consent_fail_closed(tmp_path, corpus, field, value):
    store = CalibrationStore(tmp_path / "profiles", corpus=corpus)
    sid = store.create(name="Mine", consent=True)["id"]
    path = tmp_path / "calibration" / sid / "session.json"
    data = json.loads(path.read_bytes())
    data[field] = value
    path.write_text(json.dumps(data))
    with pytest.raises(CalibrationError):
        store.get(sid)


def test_finalize_selects_neutral_preserves_session_and_export(tmp_path, corpus, signal_wav):
    import zipfile

    from voicefont.registry import ProfileStore

    store = CalibrationStore(tmp_path / "profiles", corpus=corpus)
    sid = store.create(name="Mine", consent=True)["id"]
    with pytest.raises(CalibrationError, match="3 distinct"):
        store.finalize(sid, voice_id="mine", name="Mine")
    raw = signal_wav(duration=0.5)
    store.submit_take(sid, "p1", "old", signal_wav(amplitude=0.01))
    store.submit_take(sid, "p1", "best", raw)
    store.submit_take(sid, "p2", "second", signal_wav(amplitude=0.005))
    store.submit_take(sid, "p3", "warm", signal_wav(duration=1))
    profile = store.finalize(sid, voice_id="mine", name="Mine")
    assert profile["voice_id"] == "mine"
    assert "path" not in json.dumps(profile)
    assert (
        ProfileStore(tmp_path / "profiles").get("mine").references[0].sha256
        == (store.get(sid)["takes"][1]["sha256"])
    )
    resumed = CalibrationStore(tmp_path / "profiles", corpus=corpus)
    session = resumed.get(sid)
    assert session["status"] == "finalized"
    assert session["profile_id"] == "mine"
    assert session["primary_take_id"] == "best"
    assert resumed.finalize(sid, voice_id="mine", name="Mine") == profile
    with pytest.raises(CalibrationError):
        resumed.finalize(sid, voice_id="another", name="Mine")
    with pytest.raises(CalibrationError):
        resumed.skip(sid, "p4")
    directory = tmp_path / "calibration" / sid
    (directory / "private.txt").write_text("not session-owned")
    archive = resumed.export(sid)
    try:
        with zipfile.ZipFile(archive) as z:
            assert set(z.namelist()) == {
                "session.json",
                "corpus.json",
                "takes/old.wav",
                "takes/best.wav",
                "takes/second.wav",
                "takes/warm.wav",
            }
            assert z.read("takes/best.wav") == raw
            assert json.loads(z.read("session.json"))["profile_id"] == "mine"
    finally:
        archive.close()


def test_finalize_requires_neutral_reference(tmp_path, corpus, signal_wav):
    for prompt in corpus["prompts"]:
        prompt["style"] = "warm"
    store = CalibrationStore(tmp_path / "profiles", corpus=corpus)
    sid = store.create(name="Mine", consent=True)["id"]
    for pid in ("p1", "p2", "p3"):
        store.submit_take(sid, pid, pid, signal_wav())
    with pytest.raises(CalibrationError, match="neutral"):
        store.finalize(sid, voice_id="mine", name="Mine")
    assert not (tmp_path / "profiles" / "mine").exists()


def test_skipping_all_prompts_never_claims_complete(tmp_path, corpus):
    store = CalibrationStore(tmp_path / "profiles", corpus=corpus)
    sid = store.create(name="Mine", consent=True)["id"]
    for pid in ("p1", "p2", "p3", "p4"):
        session = store.skip(sid, pid)
    assert session["next_prompt_id"] is None
    assert session["coverage"]["label"] == "partial"
    assert session["coverage"]["completed"] == 0


def test_finalize_partial_and_requires_neutral(tmp_path, corpus, signal_wav):
    store = CalibrationStore(tmp_path / "profiles", corpus=corpus)
    sid = store.create(name="Mine", consent=True)["id"]
    for p in ("p1", "p3", "p4"):
        store.submit_take(sid, p, p, signal_wav())
    store.finalize(sid, voice_id="partial", name="Partial")
    assert store.get(sid)["coverage"]["label"] == "partial"


def test_finalize_retry_recovers_after_metadata_failure(tmp_path, corpus, signal_wav, monkeypatch):
    store = CalibrationStore(tmp_path / "profiles", corpus=corpus)
    sid = store.create(name="Mine", consent=True)["id"]
    for p in ("p1", "p2", "p3"):
        store.submit_take(sid, p, p, signal_wav())
    save = store._save

    def fail_final(data):
        if data["status"] == "finalized":
            raise OSError("simulated disk failure")
        save(data)

    monkeypatch.setattr(store, "_save", fail_final)
    with pytest.raises(OSError):
        store.finalize(sid, voice_id="mine", name="Mine")
    resumed = CalibrationStore(tmp_path / "profiles", corpus=corpus)
    assert resumed.finalize(sid, voice_id="mine", name="Mine")["voice_id"] == "mine"
    assert resumed.get(sid)["status"] == "finalized"


def ready_session(tmp_path, corpus, signal_wav):
    store = CalibrationStore(tmp_path / "profiles", corpus=corpus)
    sid = store.create(name="Mine", consent=True)["id"]
    for pid in ("p1", "p2", "p3"):
        store.submit_take(sid, pid, pid, signal_wav())
    return store, sid


def test_finalize_missing_reference_allows_reselection(tmp_path, corpus, signal_wav):
    store, sid = ready_session(tmp_path, corpus, signal_wav)
    store.submit_take(sid, "p1", "replacement", signal_wav())
    store.select(sid, "p1", "p1")
    (tmp_path / "calibration" / sid / "takes/p1.wav").unlink()
    with pytest.raises(FileNotFoundError):
        store.finalize(sid, voice_id="mine", name="Mine")
    assert store.select(sid, "p1", "replacement")["accepted"]["p1"] == "replacement"
    assert store.get(sid)["pending_finalization"] is None
    assert store.finalize(sid, voice_id="new-id", name="New name")["voice_id"] == "new-id"


def test_finalize_enrollment_failure_unlocks_retry(tmp_path, corpus, signal_wav, monkeypatch):
    from voicefont.registry import ProfileStore

    store, sid = ready_session(tmp_path, corpus, signal_wav)

    def fail_enrollment(*args, **kwargs):
        raise OSError("temporary storage failure")

    with monkeypatch.context() as patch:
        patch.setattr(ProfileStore, "enroll", fail_enrollment)
        with pytest.raises(OSError):
            store.finalize(sid, voice_id="mine", name="Mine")
    store.submit_take(sid, "p1", "replacement", signal_wav())
    assert store.get(sid)["pending_finalization"] is None
    assert store.finalize(sid, voice_id="new-id", name="New name")["voice_id"] == "new-id"


def test_finalize_collision_unlocks_without_overwriting(tmp_path, corpus, signal_wav, monkeypatch):
    from voicefont.registry import ProfileStore

    store, sid = ready_session(tmp_path, corpus, signal_wav)
    enroll = ProfileStore.enroll

    def competing_enrollment(profiles, raw, **kwargs):
        enroll(profiles, signal_wav(880), voice_id=kwargs["voice_id"], name="Other", consent=True)
        raise FileExistsError("profile already exists")

    with monkeypatch.context() as patch:
        patch.setattr(ProfileStore, "enroll", competing_enrollment)
        with pytest.raises(CalibrationError, match="profile"):
            store.finalize(sid, voice_id="mine", name="Mine")
    assert store.get(sid)["pending_finalization"] is None
    assert store.finalize(sid, voice_id="new-id", name="New name")["voice_id"] == "new-id"
    assert ProfileStore(tmp_path / "profiles").get("mine").name == "Other"


def test_finalize_published_profile_recovers_without_take(
    tmp_path, corpus, signal_wav, monkeypatch
):
    store, sid = ready_session(tmp_path, corpus, signal_wav)
    save = store._save

    def fail_final(data):
        if data["status"] == "finalized":
            raise OSError("temporary metadata failure")
        save(data)

    with monkeypatch.context() as patch:
        patch.setattr(store, "_save", fail_final)
        with pytest.raises(OSError):
            store.finalize(sid, voice_id="mine", name="Mine")
    assert store.get(sid)["pending_finalization"] == {"voice_id": "mine", "name": "Mine"}
    (tmp_path / "calibration" / sid / "takes/p1.wav").unlink()
    with pytest.raises(CalibrationError):
        store.finalize(sid, voice_id="different", name="Different")
    assert store.finalize(sid, voice_id="mine", name="Mine")["voice_id"] == "mine"
    assert store.get(sid)["pending_finalization"] is None


def test_finalize_failed_rollback_can_resume_reselection(tmp_path, corpus, signal_wav, monkeypatch):
    from voicefont.registry import ProfileStore

    store, sid = ready_session(tmp_path, corpus, signal_wav)
    save = store._save

    def fail_enrollment(*args, **kwargs):
        raise OSError("temporary enrollment failure")

    def fail_rollback(data):
        if "_finalizing" not in data:
            raise OSError("temporary rollback failure")
        save(data)

    with monkeypatch.context() as patch:
        patch.setattr(ProfileStore, "enroll", fail_enrollment)
        patch.setattr(store, "_save", fail_rollback)
        with pytest.raises(OSError):
            store.finalize(sid, voice_id="mine", name="Mine")
    resumed = CalibrationStore(tmp_path / "profiles", corpus=corpus)
    resumed.submit_take(sid, "p1", "replacement", signal_wav())
    assert resumed.get(sid)["pending_finalization"] is None
    assert resumed.finalize(sid, voice_id="new-id", name="New")["voice_id"] == "new-id"


def test_finalize_enroll_published_then_raised_recovers(tmp_path, corpus, signal_wav, monkeypatch):
    from voicefont.registry import ProfileStore

    store, sid = ready_session(tmp_path, corpus, signal_wav)
    enroll = ProfileStore.enroll

    def fail_after_publish(*args, **kwargs):
        enroll(*args, **kwargs)
        raise OSError("temporary staging cleanup failure")

    monkeypatch.setattr(ProfileStore, "enroll", fail_after_publish)
    assert store.finalize(sid, voice_id="mine", name="Mine")["voice_id"] == "mine"
    assert store.get(sid)["status"] == "finalized"


def test_get_corpus_returns_detached_saved_snapshot(tmp_path, corpus):
    store = CalibrationStore(tmp_path / "profiles", corpus=corpus)
    sid = store.create(name="Mine", consent=True)["id"]
    corpus["prompts"] = []
    resumed = CalibrationStore(tmp_path / "profiles", corpus=corpus)
    snapshot = resumed.get_corpus(sid)
    assert len(snapshot["prompts"]) == 4
    snapshot["prompts"][0]["text"] = "changed"
    assert resumed.get_corpus(sid)["prompts"][0]["text"] == "p1"


def make_client(tmp_path, corpus):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from voicefont.calibration_routes import create_calibration_router

    app = FastAPI()
    app.include_router(create_calibration_router(tmp_path / "profiles", corpus=corpus))
    return TestClient(app)


def test_routes_complete_contract(tmp_path, corpus, signal_wav):
    client = make_client(tmp_path, corpus)
    assert client.get("/calibration/corpus").json() == corpus
    response = client.post(
        "/calibration/sessions",
        json={
            "name": "Mine",
            "consent": True,
            "mode": "adaptive",
        },
    )
    assert response.status_code == 201
    session = response.json()
    base = "/calibration/sessions/" + session["id"]
    assert client.get(base).json() == session
    assert client.get("/calibration/sessions").json() == [session]
    assert client.post(base + "/skip", json={"prompt_id": "p4"}).status_code == 200
    raw = signal_wav()
    for pid in ("p1", "p2", "p3"):
        take = client.post(
            base + f"/takes?prompt_id={pid}&take_id={pid}",
            content=raw,
            headers={"content-type": "audio/wav"},
        )
        assert take.status_code == 200, take.text
    assert (
        client.post(base + "/select", json={"prompt_id": "p1", "take_id": "p1"}).status_code == 200
    )
    assert client.get(base + "/takes/p1/audio").content == raw
    assert client.get(base + "/export").headers["content-type"] == "application/zip"
    finalized = client.post(base + "/finalize", json={"voice_id": "mine", "name": "Mine"})
    assert finalized.status_code == 200, finalized.text
    assert finalized.json()["voice_id"] == "mine"
    assert client.get(base).json()["status"] == "finalized"
    assert str(tmp_path) not in finalized.text


@pytest.mark.parametrize(
    "body",
    [
        {"name": "Mine", "consent": False, "mode": "full"},
        {"name": "Mine", "consent": "true", "mode": "full"},
        {"name": "Mine", "consent": 1, "mode": "full"},
        {"name": "Mine", "consent": True, "mode": "weird"},
        {"name": "Mine", "consent": True, "mode": "full", "path": "outside"},
    ],
)
def test_routes_strict_json_input(tmp_path, corpus, body):
    assert make_client(tmp_path, corpus).post("/calibration/sessions", json=body).status_code == 422


def test_routes_origin_size_media_and_errors(tmp_path, corpus, signal_wav):
    client = make_client(tmp_path, corpus)
    payload = {"name": "Mine", "consent": True, "mode": "full"}
    assert (
        client.post(
            "/calibration/sessions", json=payload, headers={"origin": "https://evil.invalid"}
        ).status_code
        == 403
    )
    assert (
        client.post("/calibration/sessions", json=payload, headers={"origin": "null"}).status_code
        == 403
    )
    same = client.post(
        "/calibration/sessions", json=payload, headers={"origin": "http://testserver"}
    )
    assert same.status_code == 201
    base = "/calibration/sessions/" + same.json()["id"]
    assert (
        client.post(
            "/calibration/sessions",
            content=b" " * 20000,
            headers={"content-type": "application/json"},
        ).status_code
        == 413
    )
    assert (
        client.post(
            "/calibration/sessions",
            content=b"not-json",
            headers={"content-type": "application/json"},
        ).status_code
        == 422
    )
    assert (
        client.post(
            base + "/takes?prompt_id=p1&take_id=t1",
            content=b"bad",
            headers={"content-type": "audio/webm"},
        ).status_code
        == 415
    )
    invalid = client.post(
        base + "/takes?prompt_id=p1&take_id=t1",
        content=b"bad",
        headers={"content-type": "audio/wav"},
    )
    assert invalid.status_code == 422
    assert "record" in invalid.json()["detail"].lower()
    assert client.get("/calibration/sessions/missing").status_code == 404
    assert client.get(base + "/takes/missing/audio").status_code == 404
    assert (
        client.post(
            base + "/takes?prompt_id=p1&take_id=CON",
            content=signal_wav(),
            headers={"content-type": "audio/wav"},
        ).status_code
        == 422
    )
    assert (
        client.post(
            base + "/takes?prompt_id=p1&take_id=t1",
            content=signal_wav(),
            headers={"content-type": "audio/wav"},
        ).status_code
        == 200
    )
    conflict = client.post(
        base + "/takes?prompt_id=p1&take_id=t1",
        content=signal_wav(880),
        headers={"content-type": "audio/wav"},
    )
    assert conflict.status_code == 409
    assert str(tmp_path) not in conflict.text


def test_atomic_replace_failure_keeps_previous_state(tmp_path, corpus, monkeypatch):
    import voicefont.calibration as module

    store = CalibrationStore(tmp_path / "profiles", corpus=corpus)
    session = store.create(name="Mine", consent=True)

    def fail_replace(*args):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(module.os, "replace", fail_replace)
    with pytest.raises(OSError):
        store.skip(session["id"], "p1")
    assert CalibrationStore(tmp_path / "profiles", corpus=corpus).get(session["id"]) == session
    assert not list((tmp_path / "calibration" / session["id"]).glob(".pending-*"))


def test_session_limits_and_bounded_stored_json(tmp_path, corpus, signal_wav, monkeypatch):
    import voicefont.calibration as module

    store = CalibrationStore(tmp_path / "profiles", corpus=corpus)
    sid = store.create(name="Mine", consent=True)["id"]
    monkeypatch.setattr(module, "MAX_TAKES", 1)
    store.submit_take(sid, "p1", "first", signal_wav())
    with pytest.raises(CalibrationError, match="limit"):
        store.submit_take(sid, "p2", "second", signal_wav())
    monkeypatch.setattr(module, "MAX_SESSIONS", 1)
    with pytest.raises(CalibrationError, match="limit"):
        store.create(name="Other", consent=True)
    metadata = tmp_path / "calibration" / sid / "session.json"
    metadata.write_bytes(b" " * (module.MAX_JSON_BYTES + 1))
    with pytest.raises(CalibrationError, match="limit"):
        store.get(sid)


@pytest.mark.parametrize("tamper", ["take-id", "accepted", "extra-path", "duplicate-take", "mode"])
def test_stored_metadata_validation_fails_closed(tmp_path, corpus, signal_wav, tamper):
    store = CalibrationStore(tmp_path / "profiles", corpus=corpus)
    sid = store.create(name="Mine", consent=True)["id"]
    store.submit_take(sid, "p1", "first", signal_wav())
    metadata = tmp_path / "calibration" / sid / "session.json"
    data = json.loads(metadata.read_bytes())
    if tamper == "take-id":
        data["takes"][0]["id"] = "../outside"
    elif tamper == "accepted":
        data["accepted"]["p2"] = "first"
    elif tamper == "extra-path":
        data["takes"][0]["path"] = str(tmp_path)
    elif tamper == "duplicate-take":
        data["takes"].append(data["takes"][0])
    else:
        data["mode"] = "something-else"
    metadata.write_text(json.dumps(data))
    with pytest.raises(CalibrationError):
        store.get(sid)


def test_linked_take_directory_is_rejected(tmp_path, corpus, signal_wav):
    import os
    import subprocess

    store = CalibrationStore(tmp_path / "profiles", corpus=corpus)
    sid = store.create(name="Mine", consent=True)["id"]
    directory = tmp_path / "calibration" / sid / "takes"
    directory.rmdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    if os.name == "nt":
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(directory), str(outside)],
            check=True,
            capture_output=True,
        )
    else:
        directory.symlink_to(outside, target_is_directory=True)
    try:
        with pytest.raises(CalibrationError, match="linked"):
            store.submit_take(sid, "p1", "first", signal_wav())
        assert not list(outside.iterdir())
    finally:
        if os.name == "nt":
            directory.rmdir()
        else:
            directory.unlink()


def test_hardlinked_take_cannot_export_external_file(tmp_path, corpus, signal_wav):
    import os

    store = CalibrationStore(tmp_path / "profiles", corpus=corpus)
    sid = store.create(name="Mine", consent=True)["id"]
    store.submit_take(sid, "p1", "first", signal_wav())
    raw = tmp_path / "calibration" / sid / "takes" / "first.wav"
    external = tmp_path / "outside.wav"
    raw.rename(external)
    os.link(external, raw)
    with pytest.raises(CalibrationError, match="linked"):
        store.export(sid)


def test_default_router_uses_real_bundled_corpus(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from voicefont.calibration_routes import create_calibration_router
    from voicefont.corpus import load_corpus

    app = FastAPI()
    app.include_router(create_calibration_router(tmp_path / "profiles"))
    client = TestClient(app)
    assert client.get("/calibration/corpus").json() == load_corpus()
    session = client.post("/calibration/sessions", json={"name": "Mine", "consent": True}).json()
    assert session["coverage"]["total"] >= 70


@pytest.fixture
def corpus():
    return {
        "version": "test-1",
        "language": "en-GB",
        "title": "Test fixture",
        "disclaimer": "Synthetic mechanics only",
        "categories": [{"id": c, "title": c, "description": c} for c in ("a", "b")],
        "prompts": [
            {
                "id": pid,
                "category": cat,
                "text": pid,
                "instruction": "Speak naturally",
                "dimensions": [],
                "optional": optional,
                "style": style,
            }
            for pid, cat, optional, style in [
                ("p1", "a", False, "neutral"),
                ("p2", "a", False, "neutral"),
                ("p3", "b", False, "warm"),
                ("p4", "b", True, "neutral"),
            ]
        ],
    }


def test_create_resume_and_consent(tmp_path, corpus):
    store = CalibrationStore(tmp_path / "profiles", corpus=corpus)
    with pytest.raises(CalibrationError, match="consent"):
        store.create(name="Mine", consent=False, mode="full")
    session = store.create(name=" Mine ", consent=True, mode="full")
    assert session["name"] == "Mine"
    assert session["consent"]["asserted"] is True
    assert session["next_prompt_id"] == "p1"
    assert session["coverage"]["completed"] == 0
    assert session["coverage"]["total"] == 4
    assert session["coverage"]["label"] == "partial"
    assert CalibrationStore(tmp_path / "profiles", corpus=corpus).get(session["id"]) == session
    assert store.list_sessions() == [session]
    assert str(tmp_path) not in json.dumps(session)
    assert (tmp_path / "calibration" / session["id"] / "session.json").is_file()


def test_skip_is_durable_and_not_coverage(tmp_path, corpus):
    store = CalibrationStore(tmp_path / "profiles", corpus=corpus)
    session = store.create(name="Mine", consent=True, mode="full")
    session = store.skip(session["id"], "p1")
    assert session["skipped"] == ["p1"]
    assert session["next_prompt_id"] == "p2"
    assert session["coverage"]["completed"] == 0
    assert CalibrationStore(tmp_path / "profiles", corpus=corpus).get(session["id"]) == session


@pytest.mark.parametrize("bad_id", ["../outside", "CON", "nul", "a/b", "", "x" * 65])
def test_unsafe_ids_rejected(tmp_path, corpus, bad_id):
    store = CalibrationStore(tmp_path / "profiles", corpus=corpus)
    with pytest.raises(CalibrationError):
        store.get(bad_id)
