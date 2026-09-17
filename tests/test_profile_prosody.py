"""Profile prosodic sidecar: written at finalize, readable without raw audio."""

import json

import pytest

from voicefont.calibration import CalibrationStore
from voicefont.registry import ProfileStore


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


def ready_store(tmp_path, corpus, signal_wav):
    store = CalibrationStore(tmp_path / "profiles", corpus=corpus)
    sid = store.create(name="Mine", consent=True)["id"]
    for pid in ("p1", "p2", "p3"):
        store.submit_take(sid, pid, pid, signal_wav())
    return store, sid


def test_finalize_writes_parseable_prosodic_sidecar(tmp_path, corpus, signal_wav):
    store, sid = ready_store(tmp_path, corpus, signal_wav)
    store.finalize(sid, voice_id="mine", name="Mine")
    raw = (tmp_path / "profiles" / "mine" / "prosody.json").read_text()
    data = json.loads(raw)
    assert data["version"] == "prosody-v1"
    assert data["energy_max"] > 0
    assert data["voiced_fraction"] > 0
    assert set(data) >= {
        "version",
        "pitch_median_hz",
        "pitch_min_hz",
        "pitch_max_hz",
        "energy_min",
        "energy_max",
        "energy_trend_per_frame",
        "voiced_fraction",
    }


def test_get_prosody_returns_sidecar_without_audio(tmp_path, corpus, signal_wav):
    store, sid = ready_store(tmp_path, corpus, signal_wav)
    store.finalize(sid, voice_id="mine", name="Mine")
    assert ProfileStore(tmp_path / "profiles").get_prosody("mine") == json.loads(
        (tmp_path / "profiles" / "mine" / "prosody.json").read_text()
    )
    assert ProfileStore(tmp_path / "profiles").get_prosody("absent") is None


def test_legacy_profile_without_sidecar_reads_as_none(tmp_path, corpus, signal_wav):
    ready_store(tmp_path, corpus, signal_wav)
    store = CalibrationStore(tmp_path / "profiles", corpus=corpus)
    sid = [s["id"] for s in store.list_sessions()][0]
    store.finalize(sid, voice_id="legacy", name="Legacy")
    (tmp_path / "profiles" / "legacy" / "prosody.json").unlink()
    assert ProfileStore(tmp_path / "profiles").get_prosody("legacy") is None


def test_public_profile_includes_prosody_summary(tmp_path, corpus, signal_wav):
    store, sid = ready_store(tmp_path, corpus, signal_wav)
    profile = store.finalize(sid, voice_id="mine", name="Mine")
    assert profile["prosody"]["version"] == "prosody-v1"
