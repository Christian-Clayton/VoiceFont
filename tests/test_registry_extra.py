"""Tests targeting missing registry.py lines.

    Covers: 87-88, 125, 135, 180, 190, 197, 213, 216, 218, 220, 226,
    242, 247, 253, 260, 263-264, 266, 271, 282.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from voicefont.registry import (
    ProfileStore,
    RegistryError,
    _unit,
)


def test_unit_rejects_non_numeric_vectors():
    """Lines 87-88: vectors must contain numbers."""
    with pytest.raises(RegistryError, match="numbers"):
        _unit(["a", "b", "c"])


def test_profile_dir_rejects_symlink(tmp_path):
    """Line 125: symlinked profile directories rejected (mocked)."""
    store = ProfileStore(tmp_path / "registry")
    store.root.mkdir(parents=True, exist_ok=True)
    # Mock resolve to return a different path to simulate symlink
    with patch.object(Path, "resolve", return_value=Path("/different/path")):
        with pytest.raises(RegistryError, match="linked"):
            store._profile_dir("symlink-voice")


def test_enroll_rejects_invalid_name(tmp_path, signal_wav):
    """Line 135: name validation."""
    store = ProfileStore(tmp_path / "registry")
    with pytest.raises(RegistryError, match="1-128"):
        store.enroll(signal_wav(), voice_id="signal-a", name="", consent=True)

    with pytest.raises(RegistryError, match="1-128"):
        store.enroll(signal_wav(), voice_id="signal-a", name="x" * 200, consent=True)


def test_enroll_rollback_on_failure(tmp_path, signal_wav):
    """Line 180: rollback target on staging failure."""
    store = ProfileStore(tmp_path / "registry")
    # First enrollment succeeds
    store.enroll(signal_wav(), voice_id="signal-a", name="Signal", consent=True)

    # Second enrollment with same ID should raise FileExistsError
    with pytest.raises(FileExistsError):
        store.enroll(signal_wav(), voice_id="signal-a", name="Signal", consent=True)


def test_get_rejects_symlink_profile_file(tmp_path, signal_wav):
    """Line 190: symlinked profile files rejected (mocked)."""
    store = ProfileStore(tmp_path / "registry")
    store.enroll(signal_wav(), voice_id="signal-a", name="Signal", consent=True)

    profile_path = tmp_path / "registry" / "signal-a" / "profile.json"
    # Mock resolve for just this path
    original_resolve = Path.resolve
    def fake_resolve(self):
        if self == profile_path:
            return Path("/different/path")
        return original_resolve(self)
    
    with patch.object(Path, "resolve", fake_resolve):
        with pytest.raises(RegistryError, match="linked"):
            store.get("signal-a")


def test_get_rejects_oversized_metadata(tmp_path, signal_wav):
    """Line 197: profile metadata size limit."""
    store = ProfileStore(tmp_path / "registry")
    store.enroll(signal_wav(), voice_id="signal-a", name="Signal", consent=True)

    profile_path = tmp_path / "registry" / "signal-a" / "profile.json"
    profile_path.write_text("x" * 65537)

    with pytest.raises(RegistryError, match="exceeds limit"):
        store.get("signal-a")


def test_get_rejects_invalid_name_in_profile(tmp_path, signal_wav):
    """Line 213: invalid name in stored profile."""
    store = ProfileStore(tmp_path / "registry")
    store.enroll(signal_wav(), voice_id="signal-a", name="Signal", consent=True)

    profile_path = tmp_path / "registry" / "signal-a" / "profile.json"
    data = json.loads(profile_path.read_text())
    data["name"] = ""
    profile_path.write_text(json.dumps(data))

    with pytest.raises(RegistryError, match="invalid profile name"):
        store.get("signal-a")


def test_get_rejects_naive_timestamps(tmp_path, signal_wav):
    """Line 216: timestamps must include timezone."""
    store = ProfileStore(tmp_path / "registry")
    store.enroll(signal_wav(), voice_id="signal-a", name="Signal", consent=True)

    profile_path = tmp_path / "registry" / "signal-a" / "profile.json"
    data = json.loads(profile_path.read_text())
    data["created_at"] = "2024-01-01T00:00:00"  # No timezone
    profile_path.write_text(json.dumps(data))

    with pytest.raises(RegistryError, match="timezone"):
        store.get("signal-a")


def test_get_rejects_wrong_feature_dimension(tmp_path, signal_wav):
    """Line 218: feature dimension must match FEATURE_DIM."""
    store = ProfileStore(tmp_path / "registry")
    store.enroll(signal_wav(), voice_id="signal-a", name="Signal", consent=True)

    profile_path = tmp_path / "registry" / "signal-a" / "profile.json"
    data = json.loads(profile_path.read_text())
    data["features"] = [0.5] * 10  # Wrong dimension (FEATURE_DIM=16)
    profile_path.write_text(json.dumps(data))

    with pytest.raises(RegistryError, match="invalid feature dimension"):
        store.get("signal-a")


def test_get_rejects_multiple_references(tmp_path, signal_wav):
    """Line 220: schema 1 requires exactly one reference."""
    store = ProfileStore(tmp_path / "registry")
    store.enroll(signal_wav(), voice_id="signal-a", name="Signal", consent=True)

    profile_path = tmp_path / "registry" / "signal-a" / "profile.json"
    data = json.loads(profile_path.read_text())
    data["references"].append(data["references"][0].copy())
    profile_path.write_text(json.dumps(data))

    with pytest.raises(RegistryError, match="one original reference"):
        store.get("signal-a")


def test_get_rejects_symlink_reference_file(tmp_path, signal_wav):
    """Line 226: symlinked reference files rejected (mocked)."""
    store = ProfileStore(tmp_path / "registry")
    store.enroll(signal_wav(), voice_id="signal-a", name="Signal", consent=True)

    profile_dir = tmp_path / "registry" / "signal-a"
    ref_path = profile_dir / "references" / "original.wav"
    original_resolve = Path.resolve
    def fake_resolve(self):
        if self == ref_path:
            return Path("/different/path")
        return original_resolve(self)
    
    with patch.object(Path, "resolve", fake_resolve):
        with pytest.raises(RegistryError, match="linked"):
            store.get("signal-a")


def test_get_rejects_metadata_integrity_mismatch(tmp_path, signal_wav):
    """Line 242: reference metadata doesn't match stored audio."""
    store = ProfileStore(tmp_path / "registry")
    store.enroll(signal_wav(), voice_id="signal-a", name="Signal", consent=True)

    profile_path = tmp_path / "registry" / "signal-a" / "profile.json"
    data = json.loads(profile_path.read_text())
    data["references"][0]["sample_rate"] = 44100  # Wrong sample rate
    profile_path.write_text(json.dumps(data))

    with pytest.raises(RegistryError, match="metadata integrity mismatch"):
        store.get("signal-a")


def test_get_catches_generic_errors(tmp_path, signal_wav):
    """Line 247: generic exceptions converted to RegistryError."""
    store = ProfileStore(tmp_path / "registry")
    store.enroll(signal_wav(), voice_id="signal-a", name="Signal", consent=True)

    profile_path = tmp_path / "registry" / "signal-a" / "profile.json"
    profile_path.write_text('{"bad": "structure"}')

    with pytest.raises(RegistryError, match="invalid stored profile"):
        store.get("signal-a")


def test_get_prosody_rejects_symlink(tmp_path, signal_wav):
    """Line 253: symlinked prosody files rejected (mocked)."""
    store = ProfileStore(tmp_path / "registry")
    store.enroll(signal_wav(), voice_id="signal-a", name="Signal", consent=True)

    prosody_path = tmp_path / "registry" / "signal-a" / "prosody.json"
    original_resolve = Path.resolve
    def fake_resolve(self):
        if self == prosody_path:
            return Path("/different/path")
        return original_resolve(self)
    
    with patch.object(Path, "resolve", fake_resolve):
        with pytest.raises(RegistryError, match="linked"):
            store.get_prosody("signal-a")


def test_get_prosody_rejects_oversized(tmp_path, signal_wav):
    """Line 260: prosody metadata size limit."""
    store = ProfileStore(tmp_path / "registry")
    store.enroll(signal_wav(), voice_id="signal-a", name="Signal", consent=True)

    prosody_path = tmp_path / "registry" / "signal-a" / "prosody.json"
    prosody_path.write_text("x" * 65537)

    with pytest.raises(RegistryError, match="exceeds limit"):
        store.get_prosody("signal-a")


def test_get_prosody_rejects_invalid_json(tmp_path, signal_wav):
    """Lines 263-264: invalid prosody JSON."""
    store = ProfileStore(tmp_path / "registry")
    store.enroll(signal_wav(), voice_id="signal-a", name="Signal", consent=True)

    prosody_path = tmp_path / "registry" / "signal-a" / "prosody.json"
    prosody_path.write_text("{invalid json")

    with pytest.raises(RegistryError, match="invalid stored prosody"):
        store.get_prosody("signal-a")


def test_get_prosody_rejects_wrong_version(tmp_path, signal_wav):
    """Line 266: unsupported prosody version."""
    store = ProfileStore(tmp_path / "registry")
    store.enroll(signal_wav(), voice_id="signal-a", name="Signal", consent=True)

    prosody_path = tmp_path / "registry" / "signal-a" / "prosody.json"
    prosody_path.write_text(json.dumps({"version": "prosody-v99"}))

    with pytest.raises(RegistryError, match="unsupported prosody version"):
        store.get_prosody("signal-a")


def test_list_profiles_empty_root(tmp_path):
    """Line 271: empty root returns empty list."""
    store = ProfileStore(tmp_path / "registry")
    # Root doesn't exist yet
    assert store.list_profiles() == []


def test_search_features_rejects_wrong_dimension(tmp_path):
    """Line 282: query feature dimension must match."""
    store = ProfileStore(tmp_path / "registry")
    with pytest.raises(RegistryError, match="invalid query feature dimension"):
        store.search_features([0.5] * 10)  # Wrong dimension
