"""Durable single-user calibration. Raw originals never change after acceptance.

Disk is owner-trusted, but identifiers, linked files and metadata fail closed.
A process mutex plus OS file lock serialize read/modify/replace transactions.
Coverage describes recorded prompts, not measured phonetic or emotional ability.
"""

from __future__ import annotations

import copy
import json
import os
import re
import threading
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from .audio import MAX_FILE_BYTES
from .registry import CONSENT_STATEMENT, RegistryError, validate_voice_id

SCHEMA_VERSION = "1.0.0"
MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_SESSIONS = 100
MAX_TAKES = 500
MAX_SESSION_BYTES = 512 * 1024 * 1024
_MUTEX = threading.RLock()
_HEX64 = re.compile(r"[0-9a-f]{64}")


class CalibrationError(ValueError):
    """Invalid calibration input or stored data."""


class CalibrationConflict(CalibrationError):
    """An immutable identifier or completed session conflicts with a mutation."""


def _identifier(value):
    try:
        return validate_voice_id(value)
    except RegistryError:
        raise CalibrationError("IDs must be safe lowercase ASCII, 1-64 characters") from None


def _name(value):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= 128:
        raise CalibrationError("name must have 1-128 characters")
    return value.strip()


def _now():
    return datetime.now(UTC).isoformat()


def _safe(path):
    if path.is_symlink() or path.resolve() != path:
        raise CalibrationError("linked storage paths are not permitted")
    return path


def _json_bytes(data):
    raw = json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8")
    if len(raw) > MAX_JSON_BYTES:
        raise CalibrationError("session metadata exceeds limit")
    return raw


class CalibrationStore:
    def __init__(self, profile_root: str | Path, *, corpus: dict | None = None):
        self.profile_root = Path(os.path.abspath(profile_root))
        _safe(self.profile_root)
        self.root = _safe(self.profile_root.parent / "calibration")
        if corpus is None:
            from .corpus import load_corpus

            corpus = load_corpus()
        self.corpus = json.loads(_json_bytes(corpus))
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    @contextmanager
    def _locked(self):
        with _MUTEX:
            path = _safe(self.root / ".lock")
            with path.open("a+b") as stream:
                stream.seek(0, 2)
                if stream.tell() == 0:
                    stream.write(b"0")
                    stream.flush()
                stream.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
                else:
                    import fcntl

                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    stream.seek(0)
                    if os.name == "nt":
                        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    def _directory(self, session_id):
        return _safe(self.root / _identifier(session_id))

    def _load(self, session_id):
        path = _safe(self._directory(session_id) / "session.json")
        try:
            with path.open("rb") as stream:
                raw = stream.read(MAX_JSON_BYTES + 1)
            if len(raw) > MAX_JSON_BYTES:
                raise CalibrationError("session metadata exceeds limit")
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise CalibrationError("stored session must be a JSON object")
            if data.get("schema_version") != SCHEMA_VERSION or data.get("id") != session_id:
                raise CalibrationError("unsupported session schema or identity")
            if data.get("mode") not in ("full", "adaptive"):
                raise CalibrationError("invalid stored session mode")
            if data.get("status") not in ("active", "finalized"):
                raise CalibrationError("invalid session status")
            consent = data.get("consent")
            if (
                not isinstance(consent, dict)
                or consent.get("asserted") is not True
                or consent.get("statement") != CONSENT_STATEMENT
                or not isinstance(consent.get("asserted_at"), str)
            ):
                raise CalibrationError("session consent is not active")
            for key in ("name", "created_at", "updated_at", "mode", "corpus_version"):
                if not isinstance(data.get(key), str) or not data[key]:
                    raise CalibrationError("stored session has an invalid " + key)
            accepted = data.get("accepted")
            skipped = data.get("skipped")
            takes = data.get("takes")
            if (
                not isinstance(accepted, dict)
                or not all(isinstance(v, str) for v in accepted.values())
                or not isinstance(skipped, list)
                or not all(isinstance(v, str) for v in skipped)
                or not isinstance(takes, list)
            ):
                raise CalibrationError("stored session has invalid coverage state")
            if len({take.get("id") for take in takes}) != len(takes):
                raise CalibrationError("duplicate take identifiers")
            prompt_ids = {prompt["id"] for prompt in data["_corpus"]["prompts"]}
            prompt_styles = {prompt["style"] for prompt in data["_corpus"]["prompts"]}
            seen = set()
            for take in takes:
                if (
                    not isinstance(take, dict)
                    or set(take)
                    != {"id", "prompt_id", "duration_seconds", "sha256", "quality", "style"}
                    or _identifier(take["id"]) != take["id"]
                    or take["prompt_id"] not in prompt_ids
                    or not _HEX64.fullmatch(take["sha256"])
                    or not isinstance(take["duration_seconds"], int | float)
                    or not 0.1 <= take["duration_seconds"] <= 180
                    or not isinstance(take["quality"], dict)
                    or set(take["quality"]) != {"rms", "peak", "clipping_fraction"}
                    or take["style"] not in prompt_styles
                ):
                    raise CalibrationError("stored take metadata is invalid")
                if take["id"] in seen:
                    raise CalibrationError("duplicate take identifiers")
                seen.add(take["id"])
            if accepted.keys() - prompt_ids or set(accepted.values()) - seen:
                raise CalibrationError("accepted take references are invalid")
            by_id = {take["id"]: take for take in takes}
            if any(by_id[tid]["prompt_id"] != pid for pid, tid in accepted.items()):
                raise CalibrationError("accepted take belongs to a different prompt")
            if not set(skipped) <= prompt_ids or set(skipped) & accepted.keys():
                raise CalibrationError("skipped prompts are invalid")
            _name(data["name"])
            for timestamp in (data["created_at"], data["updated_at"], consent["asserted_at"]):
                if datetime.fromisoformat(timestamp).tzinfo is None:
                    raise CalibrationError("stored timestamps require timezone")
            for take in takes:
                if any(
                    type(v) not in (int, float) or not 0 <= v <= 1 for v in take["quality"].values()
                ):
                    raise CalibrationError("invalid quality metrics")
                if self._prompt(data, take["prompt_id"])["style"] != take["style"]:
                    raise CalibrationError("take style does not match prompt")
            if len(takes) > MAX_TAKES or len(skipped) != len(set(skipped)):
                raise CalibrationError("invalid stored take or skip count")
            allowed = {
                "schema_version",
                "id",
                "name",
                "created_at",
                "updated_at",
                "consent",
                "mode",
                "corpus_version",
                "accepted",
                "skipped",
                "takes",
                "status",
                "profile_id",
                "primary_take_id",
                "_corpus",
                "_finalizing",
            }
            if data.keys() - allowed:
                raise CalibrationError("unknown stored session fields")
            if "_finalizing" in data:
                intent = data["_finalizing"]
                if (
                    data["status"] != "active"
                    or not isinstance(intent, dict)
                    or set(intent) != {"voice_id", "name", "take_id", "sha256"}
                    or _identifier(intent["voice_id"]) != intent["voice_id"]
                    or _name(intent["name"]) != intent["name"]
                    or intent["take_id"] not in accepted.values()
                    or by_id[intent["take_id"]]["sha256"] != intent["sha256"]
                ):
                    raise CalibrationError("invalid pending finalization")
            return data
        except FileNotFoundError:
            raise FileNotFoundError("session not found") from None
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            if isinstance(exc, CalibrationError):
                raise
            raise CalibrationError("invalid stored session") from exc

    def _save(self, data):
        directory = self._directory(data["id"])
        target = _safe(directory / "session.json")
        raw = _json_bytes(data)
        temp = directory / (".pending-" + uuid.uuid4().hex)
        try:
            with temp.open("xb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, target)
        finally:
            temp.unlink(missing_ok=True)

    def _public(self, data):
        result = {k: copy.deepcopy(v) for k, v in data.items() if not k.startswith("_")}
        prompts = data["_corpus"]["prompts"]
        accepted = data["accepted"]
        by_category = {
            c["id"]: {
                "completed": sum(p["id"] in accepted for p in prompts if p["category"] == c["id"]),
                "total": sum(p["category"] == c["id"] for p in prompts),
            }
            for c in data["_corpus"]["categories"]
        }
        result["coverage"] = {
            "completed": len(accepted),
            "total": len(prompts),
            "by_category": by_category,
            "label": "complete"
            if all(p["id"] in accepted for p in prompts if not p["optional"])
            else "partial",
        }
        pending = [p for p in prompts if p["id"] not in accepted and p["id"] not in data["skipped"]]
        if data["mode"] == "adaptive":
            pending.sort(key=lambda p: by_category[p["category"]]["completed"])
        result["next_prompt_id"] = pending[0]["id"] if pending else None
        intent = data.get("_finalizing")
        result["pending_finalization"] = (
            {"voice_id": intent["voice_id"], "name": intent["name"]} if intent else None
        )
        return result

    def _pending_profile(self, data):
        """Return a verified matching publication; unreadable storage keeps the intent."""
        from .registry import ProfileStore

        intent = data["_finalizing"]
        try:
            profile = ProfileStore(self.profile_root).get(intent["voice_id"])
        except FileNotFoundError:
            return None
        if profile.name == intent["name"] and profile.references[0].sha256 == intent["sha256"]:
            return profile
        return None

    def _clear_intent(self, data):
        updated = copy.deepcopy(data)
        updated.pop("_finalizing", None)
        updated["updated_at"] = _now()
        self._save(updated)
        data.clear()
        data.update(updated)

    def _active(self, data):
        if data["status"] != "active":
            raise CalibrationConflict("session is finalized")
        if "_finalizing" in data:
            if self._pending_profile(data) is not None:
                raise CalibrationConflict("finish the existing finalization request first")
            # Also recovers a crash or a failed rollback before publication.
            self._clear_intent(data)

    def _take(self, data, take_id):
        _identifier(take_id)
        for take in data["takes"]:
            if take["id"] == take_id:
                return take
        raise FileNotFoundError("take not found")

    def submit_take(self, session_id, prompt_id, take_id, raw):
        import hashlib

        import numpy as np

        from .audio import read_audio

        _identifier(take_id)
        if not isinstance(raw, bytes) or len(raw) > MAX_FILE_BYTES:
            raise CalibrationError("take exceeds maximum bytes or is not raw WAV")
        with self._locked():
            data = self._load(session_id)
            prompt = self._prompt(data, prompt_id)
            for known in data["takes"]:
                if known["id"] == take_id:
                    if (
                        known["prompt_id"] != prompt_id
                        or known["sha256"] != hashlib.sha256(raw).hexdigest()
                    ):
                        raise CalibrationConflict("take_id conflict: prompt or bytes differ")
                    self._audio(data, take_id)
                    return self._public(data)
            self._active(data)
            directory = _safe(self._directory(session_id) / "takes")
            target = _safe(directory / f"{take_id}.wav")
            exists = target.exists()
            if exists:
                with target.open("rb") as stream:
                    existing = stream.read(MAX_FILE_BYTES + 1)
                if existing != raw:
                    raise CalibrationConflict("take_id conflict: stored bytes differ")
            if len(data["takes"]) >= MAX_TAKES:
                raise CalibrationError("take limit reached")
            size = sum(_safe(p).stat().st_size for p in directory.iterdir())
            if size + (0 if exists else len(raw)) > MAX_SESSION_BYTES:
                raise CalibrationError("session audio limit reached")
            audio = read_audio(raw)
            quality = {
                "rms": float(np.sqrt(np.mean((audio.samples - audio.samples.mean()) ** 2))),
                "peak": float(np.max(np.abs(audio.samples))),
                "clipping_fraction": float(np.mean(np.abs(audio.samples) >= 0.999)),
            }
            if not exists:
                temp = directory / (".pending-" + uuid.uuid4().hex)
                try:
                    with temp.open("xb") as stream:
                        stream.write(raw)
                        stream.flush()
                        os.fsync(stream.fileno())
                    # Target absence checked under the cross-process lock. Never replace a take.
                    os.link(temp, target)
                finally:
                    temp.unlink(missing_ok=True)
            data["takes"].append(
                {
                    "id": take_id,
                    "prompt_id": prompt_id,
                    "duration_seconds": audio.duration_seconds,
                    "sha256": audio.sha256,
                    "quality": quality,
                    "style": prompt["style"],
                }
            )
            data["accepted"][prompt_id] = take_id
            data["skipped"] = [p for p in data["skipped"] if p != prompt_id]
            data["updated_at"] = _now()
            self._save(data)
            return self._public(data)

    def select(self, session_id, prompt_id, take_id):
        with self._locked():
            data = self._load(session_id)
            self._active(data)
            self._prompt(data, prompt_id)
            take = self._take(data, take_id)
            if take["prompt_id"] != prompt_id:
                raise CalibrationConflict("take belongs to a different prompt")
            self._audio(data, take_id)
            updated = copy.deepcopy(data)
            updated["accepted"][prompt_id] = take_id
            updated["updated_at"] = _now()
            self._save(updated)
            return self._public(updated)

    def _audio(self, data, take_id):
        import hashlib

        take = self._take(data, take_id)
        target = _safe(self._directory(data["id"]) / "takes" / f"{take_id}.wav")
        try:
            links = _safe(target).stat().st_nlink
        except FileNotFoundError:
            raise FileNotFoundError("take audio not found") from None
        if links > 1:
            raise CalibrationError("linked take files are not permitted")
        with target.open("rb") as stream:
            raw = stream.read(MAX_FILE_BYTES + 1)
        if len(raw) > MAX_FILE_BYTES or hashlib.sha256(raw).hexdigest() != take["sha256"]:
            raise CalibrationError("stored take integrity check failed")
        return raw

    def audio(self, session_id, take_id):
        with self._locked():
            return self._audio(self._load(session_id), take_id)

    def _profile_public(self, profile):
        result = profile.to_dict()
        for reference in result["references"]:
            reference.pop("path", None)
        return result

    def _complete_finalization(self, data, profile):
        intent = data["_finalizing"]
        data["status"] = "finalized"
        data["profile_id"] = intent["voice_id"]
        data["primary_take_id"] = intent["take_id"]
        data["updated_at"] = _now()
        data.pop("_finalizing")
        self._save(data)
        return self._profile_public(profile)

    def finalize(self, session_id, *, voice_id, name):
        """Validate before intent; roll back unpublished work or recover forward."""
        from .registry import ProfileStore

        _identifier(voice_id)
        name = _name(name)
        with self._locked():
            data = self._load(session_id)
            profiles = ProfileStore(self.profile_root)
            if data["status"] == "finalized":
                profile = profiles.get(data["profile_id"])
                if data["profile_id"] != voice_id or profile.name != name:
                    raise CalibrationConflict("session already finalized with another profile")
                return self._profile_public(profile)
            if "_finalizing" in data:
                profile = self._pending_profile(data)
                if profile is not None:
                    intent = data["_finalizing"]
                    if intent["voice_id"] != voice_id or intent["name"] != name:
                        raise CalibrationConflict("finish the existing finalization request first")
                    return self._complete_finalization(data, profile)
                self._clear_intent(data)
            accepted = [self._take(data, tid) for tid in data["accepted"].values()]
            categories = {self._prompt(data, t["prompt_id"])["category"] for t in accepted}
            if len(accepted) < 3 or len(categories) < 2:
                raise CalibrationError("record at least 3 distinct prompts across 2 categories")
            neutral = [t for t in accepted if t["style"] == "neutral"]
            if not neutral:
                raise CalibrationError("record a neutral prompt for the primary reference")
            # Heuristic signal quality only, not an assessment of identity or voice quality.
            primary = min(
                neutral,
                key=lambda t: (
                    t["quality"]["clipping_fraction"],
                    not 0.01 <= t["quality"]["rms"] <= 0.4,
                    -min(t["duration_seconds"], 30),
                    t["id"],
                ),
            )
            intent = {
                "voice_id": voice_id,
                "name": name,
                "take_id": primary["id"],
                "sha256": primary["sha256"],
            }
            raw = self._audio(data, primary["id"])
            if _safe(self.profile_root / voice_id).exists():
                raise CalibrationConflict("profile already exists")
            data["_finalizing"] = intent
            self._save(data)
            try:
                profile = profiles.enroll(raw, voice_id=voice_id, name=name, consent=True)
            except Exception as exc:
                # Enrollment can raise after publishing (e.g. staging cleanup).
                # Only a verified match commits; an unreadable registry stays pending.
                profile = self._pending_profile(data)
                if profile is None:
                    self._clear_intent(data)
                    if isinstance(exc, FileExistsError):
                        raise CalibrationConflict("profile already exists") from None
                    raise
            return self._complete_finalization(data, profile)

    def export(self, session_id):
        import tempfile
        import zipfile

        # Disk-backed, bounded backup; caller owns closing this private temporary stream.
        with self._locked():
            data = self._load(session_id)
            archive = tempfile.TemporaryFile(mode="w+b", dir=self._directory(session_id))
            try:
                with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as bundle:
                    bundle.writestr("session.json", _json_bytes(self._public(data)))
                    bundle.writestr("corpus.json", _json_bytes(data["_corpus"]))
                    total = 0
                    for take in data["takes"]:
                        raw = self._audio(data, take["id"])
                        total += len(raw)
                        if total > MAX_SESSION_BYTES:
                            raise CalibrationError("session audio limit reached")
                        bundle.writestr(f"takes/{_identifier(take['id'])}.wav", raw)
                archive.seek(0)
                return archive
            except BaseException:
                archive.close()
                raise

    def _prompt(self, data, prompt_id):
        _identifier(prompt_id)
        for prompt in data["_corpus"]["prompts"]:
            if prompt["id"] == prompt_id:
                return prompt
        raise CalibrationError("unknown prompt_id")

    def create(self, *, name, consent, mode="full"):
        if consent is not True:
            raise CalibrationError("explicit consent=true required")
        name = _name(name)
        if mode not in ("full", "adaptive"):
            raise CalibrationError("mode must be full or adaptive")
        with self._locked():
            if sum(not p.name.startswith(".") for p in self.root.iterdir()) >= MAX_SESSIONS:
                raise CalibrationError("session limit reached; back up existing sessions")
            timestamp = _now()
            data = {
                "schema_version": SCHEMA_VERSION,
                "id": uuid.uuid4().hex,
                "name": name,
                "created_at": timestamp,
                "updated_at": timestamp,
                "consent": {
                    "asserted": True,
                    "statement": CONSENT_STATEMENT,
                    "asserted_at": timestamp,
                },
                "mode": mode,
                "corpus_version": self.corpus["version"],
                "accepted": {},
                "skipped": [],
                "takes": [],
                "status": "active",
                "_corpus": self.corpus,
            }
            directory = self._directory(data["id"])
            directory.mkdir(mode=0o700)
            (directory / "takes").mkdir(mode=0o700)
            self._save(data)
            return self._public(data)

    def get(self, session_id):
        with self._locked():
            return self._public(self._load(session_id))

    def get_corpus(self, session_id):
        with self._locked():
            return copy.deepcopy(self._load(session_id)["_corpus"])

    def list_sessions(self):
        with self._locked():
            return [
                self._public(self._load(p.name))
                for p in sorted(self.root.iterdir())
                if not p.name.startswith(".") and (p / "session.json").exists()
            ]

    def skip(self, session_id, prompt_id):
        with self._locked():
            data = self._load(session_id)
            self._active(data)
            self._prompt(data, prompt_id)
            if prompt_id in data["accepted"]:
                raise CalibrationConflict(
                    "accepted prompts cannot be skipped; recordings are preserved"
                )
            if prompt_id not in data["skipped"]:
                data["skipped"].append(prompt_id)
                data["updated_at"] = _now()
                self._save(data)
            return self._public(data)
