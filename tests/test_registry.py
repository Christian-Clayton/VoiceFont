import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from voicefont.registry import ProfileStore, RegistryError, cosine_similarity


def test_consent_required_before_any_storage(signal_wav, tmp_path):
    store = ProfileStore(tmp_path / "registry")
    for consent in (False, None, "yes", 1):
        with pytest.raises(RegistryError, match="consent"):
            store.enroll(signal_wav(), voice_id="signal-a", name="Signal fixture", consent=consent)
    assert not list(store.root.glob("signal-*"))


def test_enroll_roundtrip_version_provenance_and_no_overwrite(signal_wav, tmp_path):
    store = ProfileStore(tmp_path)
    raw = signal_wav()
    profile = store.enroll(raw, voice_id="signal-a", name="Signal fixture", consent=True)
    assert profile.schema_version == "1.0.0"
    assert profile.feature_version == "acoustic-v1"
    assert profile.consent.asserted is True
    assert profile.consent.statement == "I own this voice or have explicit permission to enroll it."
    assert (tmp_path / "signal-a" / profile.references[0].path).read_bytes() == raw
    assert ProfileStore(tmp_path).get("signal-a") == profile
    assert store.list_profiles() == [profile]
    with pytest.raises(FileExistsError):
        store.enroll(raw, voice_id="signal-a", name="Other", consent=True)
    assert store.get("signal-a") == profile


@pytest.mark.parametrize(
    "voice_id",
    [
        "../x",
        "/absolute",
        "a/b",
        "a\\b",
        "CON",
        "nul",
        "aux",
        "com1",
        "lpt9",
        "MixedCase",
        "a.",
        "",
        "a" * 65,
    ],
)
def test_unsafe_ids_rejected_before_writing(signal_wav, tmp_path, voice_id):
    with pytest.raises(RegistryError):
        ProfileStore(tmp_path).enroll(signal_wav(), voice_id=voice_id, name="Signal", consent=True)
    assert list(tmp_path.iterdir()) == []


def test_concurrent_duplicate_enrollment_has_one_winner(signal_wav, tmp_path):
    raw = signal_wav()

    def enroll(_):
        try:
            return ProfileStore(tmp_path).enroll(raw, voice_id="same", name="Signal", consent=True)
        except FileExistsError:
            return None

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(enroll, range(4)))
    assert sum(result is not None for result in results) == 1
    assert len(ProfileStore(tmp_path).list_profiles()) == 1


def test_local_search_sorted_top_k_and_persistent(signal_wav, tmp_path):
    store = ProfileStore(tmp_path)
    for voice_id, freq in [("z-same", 440), ("a-same", 440), ("different", 2400)]:
        store.enroll(signal_wav(frequency=freq), voice_id=voice_id, name=voice_id, consent=True)
    matches = ProfileStore(tmp_path).search(signal_wav(), top_k=2)
    assert [match.voice_id for match in matches] == ["a-same", "z-same"]
    assert matches[0].score == pytest.approx(1)
    assert store.search_by_id("different", top_k=1)[0].voice_id == "different"
    for k in (0, -1, 101, True, 1.5):
        with pytest.raises(RegistryError):
            store.search(signal_wav(), top_k=k)


@pytest.mark.parametrize("vector", [[0, 0], [float("nan"), 1], [float("inf"), 1], []])
def test_similarity_rejects_bad_vectors(vector):
    with pytest.raises(RegistryError):
        cosine_similarity(vector, vector)


def test_similarity_validates_dimension_and_handles_large_finite_values():
    with pytest.raises(RegistryError):
        cosine_similarity([1, 2], [1])
    assert cosine_similarity([1e308, 1e308], [1e308, 1e308]) == pytest.approx(1)
    assert cosine_similarity([1, 0], [0, 1]) == 0


@pytest.mark.parametrize(
    "field,value",
    [("schema_version", "99"), ("features", [0] * 16), ("feature_version", "unknown")],
)
def test_corrupt_profiles_fail_closed(signal_wav, tmp_path, field, value):
    store = ProfileStore(tmp_path)
    store.enroll(signal_wav(), voice_id="signal", name="Signal", consent=True)
    path = tmp_path / "signal/profile.json"
    profile = json.loads(path.read_text())
    profile[field] = value
    path.write_text(json.dumps(profile))
    with pytest.raises(RegistryError):
        store.get("signal")


def test_reference_tampering_and_traversal_rejected(signal_wav, tmp_path):
    store = ProfileStore(tmp_path)
    profile = store.enroll(signal_wav(), voice_id="signal", name="Signal", consent=True)
    raw_path = tmp_path / "signal" / profile.references[0].path
    raw_path.write_bytes(signal_wav(frequency=900))
    with pytest.raises(RegistryError, match="integrity"):
        store.get("signal")
    path = tmp_path / "signal/profile.json"
    data = json.loads(path.read_text())
    data["references"][0]["path"] = "../elsewhere.wav"
    path.write_text(json.dumps(data))
    with pytest.raises(RegistryError):
        store.get("signal")
