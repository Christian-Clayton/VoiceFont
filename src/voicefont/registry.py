"""Immutable local profile bundles. Acoustic similarity is not speaker identification.

Schema 1.0.0 stores an explicit permission assertion, UTC timestamp, byte-exact
SHA256 references, and versioned deterministic descriptors. Unsupported schemas
fail closed; migration is deliberately not implicit. Local disk is owner-trusted.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from .audio import FEATURE_DIM, FEATURE_VERSION, MAX_FILE_BYTES, extract_features, read_audio

PROFILE_FORMAT_VERSION = "1.0.0"
CONSENT_STATEMENT = "I own this voice or have explicit permission to enroll it."
_RESERVED = {"con", "prn", "aux", "nul"} | {
    f"{stem}{digit}" for stem in ("com", "lpt") for digit in "123456789"
}


class RegistryError(ValueError):
    """Invalid identity, stored data, consent, or similarity request."""


def validate_voice_id(voice_id: str) -> str:
    if (
        not isinstance(voice_id, str)
        or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", voice_id)
        or voice_id in _RESERVED
    ):
        raise RegistryError("voice_id must be safe lowercase ASCII, 1-64 characters")
    return voice_id


@dataclass(frozen=True)
class ConsentRecord:
    asserted: bool
    statement: str
    asserted_at: str


@dataclass(frozen=True)
class ReferenceRecord:
    path: str
    sha256: str
    size_bytes: int
    sample_rate: int
    channels: int
    sample_width: int
    duration_seconds: float


@dataclass(frozen=True)
class Profile:
    schema_version: str
    voice_id: str
    name: str
    created_at: str
    consent: ConsentRecord
    references: list[ReferenceRecord]
    feature_version: str
    features: list[float]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Match:
    voice_id: str
    name: str
    score: float


def _unit(vector) -> np.ndarray:
    try:
        values = np.asarray(vector, dtype=np.float64)
    except (ValueError, TypeError) as exc:
        raise RegistryError("vectors must contain numbers") from exc
    if values.ndim != 1 or values.size == 0 or not np.isfinite(values).all():
        raise RegistryError("vectors must be nonempty finite one-dimensional arrays")
    scale = np.max(np.abs(values))
    if scale == 0:
        raise RegistryError("vectors must be nonzero")
    scaled = values / scale
    return scaled / np.linalg.norm(scaled)


def cosine_similarity(a, b) -> float:
    """Stable cosine for finite nonzero vectors, including extreme magnitudes."""
    left, right = _unit(a), _unit(b)
    if left.shape != right.shape:
        raise RegistryError("vectors must have equal dimensions")
    return float(np.clip(np.dot(left, right), -1, 1))


def _top_k(top_k: int) -> None:
    if type(top_k) is not int or not 1 <= top_k <= 100:
        raise RegistryError("top_k must be an integer in 1-100")


class ProfileStore:
    """One immutable bundle per voice ID; duplicate enrollment raises FileExistsError.

    Builds in a private staging directory then publishes with exclusive mkdir and
    profile.json last. Readers skip incomplete bundles. No raw-original overwrite.
    The owner controls root; HTTP clients never choose filesystem paths.
    """

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()

    def _profile_dir(self, voice_id: str) -> Path:
        target = self.root / validate_voice_id(voice_id)
        if target.resolve() != target:
            raise RegistryError("linked profile directories are not permitted")
        return target

    def enroll(
        self, reference: str | Path | bytes, *, voice_id: str, name: str, consent: bool = False
    ) -> Profile:
        if consent is not True:
            raise RegistryError(f"explicit consent required: {CONSENT_STATEMENT}")
        target = self._profile_dir(voice_id)
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 128:
            raise RegistryError("name must have 1-128 characters")
        if target.exists():
            raise FileExistsError("profile already exists")
        audio = read_audio(reference)
        timestamp = datetime.now(UTC).isoformat()
        profile = Profile(
            PROFILE_FORMAT_VERSION,
            voice_id,
            name.strip(),
            timestamp,
            ConsentRecord(True, CONSENT_STATEMENT, timestamp),
            [
                ReferenceRecord(
                    "references/original.wav",
                    audio.sha256,
                    len(audio.raw_bytes),
                    audio.sample_rate,
                    audio.channels,
                    audio.sample_width,
                    audio.duration_seconds,
                )
            ],
            FEATURE_VERSION,
            extract_features(audio).tolist(),
        )
        self.root.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix=".enroll-", dir=self.root))
        owns_target = False
        try:
            (stage / "references").mkdir()
            with (stage / "references/original.wav").open("xb") as stream:
                stream.write(audio.raw_bytes)
            with (stage / "profile.json").open("x", encoding="utf-8") as stream:
                json.dump(profile.to_dict(), stream, indent=2, allow_nan=False)
            target.mkdir()  # Atomic exclusive reservation, including across processes.
            owns_target = True
            (stage / "references").rename(target / "references")
            (stage / "profile.json").rename(target / "profile.json")
        except BaseException:
            if owns_target:
                shutil.rmtree(target)
            raise
        finally:
            shutil.rmtree(stage)
        return profile

    def get(self, voice_id: str) -> Profile:
        directory = self._profile_dir(voice_id)
        path = directory / "profile.json"
        if path.resolve() != path:
            raise RegistryError("linked profile files are not permitted")
        try:
            with path.open("rb") as stream:
                raw = stream.read(65537)
        except FileNotFoundError:
            raise FileNotFoundError("profile not found") from None
        if len(raw) > 65536:
            raise RegistryError("profile metadata exceeds limit")
        try:
            data = json.loads(raw)
            data["consent"] = ConsentRecord(**data["consent"])
            data["references"] = [ReferenceRecord(**item) for item in data["references"]]
            profile = Profile(**data)
            if profile.schema_version != PROFILE_FORMAT_VERSION:
                raise RegistryError("unsupported schema_version")
            if profile.voice_id != voice_id or profile.feature_version != FEATURE_VERSION:
                raise RegistryError("profile identity or feature version mismatch")
            if (
                profile.consent.asserted is not True
                or profile.consent.statement != CONSENT_STATEMENT
            ):
                raise RegistryError("profile is missing explicit consent")
            if not isinstance(profile.name, str) or not 1 <= len(profile.name.strip()) <= 128:
                raise RegistryError("invalid profile name")
            for timestamp in (profile.created_at, profile.consent.asserted_at):
                if datetime.fromisoformat(timestamp).tzinfo is None:
                    raise RegistryError("timestamps must include timezone")
            if len(_unit(profile.features)) != FEATURE_DIM:
                raise RegistryError("invalid feature dimension")
            if len(profile.references) != 1:
                raise RegistryError("schema 1 requires one original reference")
            reference = profile.references[0]
            if reference.path != "references/original.wav":
                raise RegistryError("invalid reference path")
            reference_path = directory / reference.path
            if reference_path.resolve() != reference_path:
                raise RegistryError("linked reference files are not permitted")
            with reference_path.open("rb") as stream:
                audio_bytes = stream.read(MAX_FILE_BYTES + 1)
            if (
                len(audio_bytes) > MAX_FILE_BYTES
                or len(audio_bytes) != reference.size_bytes
                or hashlib.sha256(audio_bytes).hexdigest() != reference.sha256
            ):
                raise RegistryError("reference integrity mismatch")
            audio = read_audio(audio_bytes)
            if (
                audio.sample_rate != reference.sample_rate
                or audio.channels != reference.channels
                or audio.sample_width != reference.sample_width
                or audio.duration_seconds != reference.duration_seconds
            ):
                raise RegistryError("reference metadata integrity mismatch")
            return profile
        except (KeyError, TypeError, ValueError, OSError) as exc:
            if isinstance(exc, RegistryError):
                raise
            raise RegistryError("invalid stored profile") from exc

    def list_profiles(self) -> list[Profile]:
        if not self.root.exists():
            return []
        return [
            self.get(entry.name)
            for entry in sorted(self.root.iterdir())
            if not entry.name.startswith(".") and (entry / "profile.json").is_file()
        ]

    def search_features(self, features, *, top_k: int = 5) -> list[Match]:
        """Rank acoustic vectors descending; ID ascending breaks ties, self included."""
        _top_k(top_k)
        if len(_unit(features)) != FEATURE_DIM:
            raise RegistryError("invalid query feature dimension")
        matches = [
            Match(p.voice_id, p.name, cosine_similarity(features, p.features))
            for p in self.list_profiles()
        ]
        return sorted(matches, key=lambda match: (-match.score, match.voice_id))[:top_k]

    def search(self, reference: str | Path | bytes, *, top_k: int = 5) -> list[Match]:
        _top_k(top_k)
        return self.search_features(extract_features(read_audio(reference)), top_k=top_k)

    def search_by_id(self, voice_id: str, *, top_k: int = 5) -> list[Match]:
        """Search with a stored descriptor; self is included for transparent ranking."""
        return self.search_features(self.get(voice_id).features, top_k=top_k)
