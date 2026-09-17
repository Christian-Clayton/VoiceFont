"""Opt-in local acoustic experiment, never TTS or speaker identity training.

One non-queued background job per local process and storage root. Original WAVs
remain in calibration storage; results contain only safe JSON and numeric models.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import os
import re
import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from .audio import FEATURE_VERSION, extract_features, read_audio
from .calibration import CalibrationStore

MIN_RECORDINGS = 8
MAX_RECORDINGS = 100
MAX_AUDIO_BYTES = 128 * 1024 * 1024
MAX_AUDIO_SECONDS = 1800
MAX_EXPERIMENTS = 100
MAX_RESULT_BYTES = 256 * 1024
LIMITATIONS = (
    "Experimental acoustic feature reconstruction, not TTS, voice cloning or speaker "
    "identity training. One vector per distinct original WAV; no text conditioning. "
    "A small within-session heldout split does not establish generalisation to other "
    "sessions, microphones or speakers. Passing the gate does not measure speech quality. "
    "Published means numeric weights in a local registry, not a speech voice."
)
CONSENT = "I authorise local acoustic model training on this session's selected recordings."
_BUSY = threading.Lock()
_RESULT_LOCK = threading.RLock()
logger = logging.getLogger(__name__)


class ExperimentError(ValueError):
    """Invalid request or unsafe local data."""


class ExperimentBusy(ExperimentError):
    """One experiment is already running; there is no queue."""


def _now():
    return datetime.now(UTC).isoformat()


def _safe(path):
    if path.is_symlink() or path.resolve() != path:
        raise ExperimentError("linked experiment storage is not permitted")
    if path.is_file() and path.stat().st_nlink > 1:
        raise ExperimentError("linked experiment files are not permitted")
    return path


def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{32}", value):
        raise ExperimentError("experiment ID must be 32 lowercase hexadecimal characters")
    return value


def capabilities():
    available = all(
        importlib.util.find_spec(name) is not None for name in ("sklearn", "langgraph", "mlflow")
    )
    return {
        "available": available,
        "message": "Local acoustic ML is installed."
        if available
        else "Install VoiceFont's ml extra before training; no runtime downloads.",
        "minimum_distinct_recordings": MIN_RECORDINGS,
        "maximum_recordings": MAX_RECORDINGS,
        "maximum_audio_seconds": MAX_AUDIO_SECONDS,
        "maximum_audio_bytes": MAX_AUDIO_BYTES,
        "maximum_concurrent_jobs": 1,
        "limitations": LIMITATIONS,
    }


def _selected(session):
    selected = set(session["accepted"].values())
    # Sorting makes the immutable snapshot reproducible, independent of UI order.
    by_hash = {}
    for take in sorted(session["takes"], key=lambda take: take["id"]):
        if take["id"] in selected:
            by_hash.setdefault(take["sha256"], take)
    takes = [by_hash[key] for key in sorted(by_hash)]
    if len(takes) < MIN_RECORDINGS:
        raise ExperimentError(
            f"record at least {MIN_RECORDINGS} distinct original WAVs; "
            "duplicate audio does not count"
        )
    if len(takes) > MAX_RECORDINGS or sum(t["duration_seconds"] for t in takes) > MAX_AUDIO_SECONDS:
        raise ExperimentError("selected recordings exceed the bounded experiment size")
    return takes


@dataclass
class SessionDataset:
    features: np.ndarray
    recording_ids: list[str]


def session_dataset(store: CalibrationStore, session: dict) -> SessionDataset:
    """Read only snapshotted selections through the store's integrity-checked API."""
    rows, groups = [], []
    total_bytes = 0
    for take in _selected(session):
        raw = store.audio(session["id"], take["id"])
        total_bytes += len(raw)
        if total_bytes > MAX_AUDIO_BYTES:
            raise ExperimentError("selected audio exceeds experiment byte limit")
        audio = read_audio(raw)
        if audio.sha256 != take["sha256"]:
            raise ExperimentError("selected audio changed after consent")
        rows.append(extract_features(audio))
        groups.append(audio.sha256)
    return SessionDataset(np.asarray(rows), groups)


class _Lease:
    """Nonblocking OS lock survives manager recreation; released on process death."""

    def __init__(self, root):
        if not _BUSY.acquire(blocking=False):
            raise ExperimentBusy("an experiment is already running; wait for it to finish")
        self.stream = None
        try:
            self.stream = _safe(root / ".worker.lock").open("a+b")
            self.stream.seek(0, 2)
            if not self.stream.tell():
                self.stream.write(b"0")
                self.stream.flush()
            self.stream.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            if self.stream:
                self.stream.close()
            _BUSY.release()
            raise ExperimentBusy(
                "an experiment is already running or its lock is unavailable"
            ) from None
        except BaseException:
            if self.stream:
                self.stream.close()
            _BUSY.release()
            raise

    def close(self):
        # Closing the handle releases either platform's file lock.
        self.stream.close()
        _BUSY.release()


class ExperimentService:
    def __init__(self, profile_root: str | Path):
        self.store = CalibrationStore(profile_root)
        self.root = _safe(self.store.profile_root.parent / "experiments")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            lease = _Lease(self.root)
        except ExperimentBusy:
            return
        try:
            # Never silently restart training after a crash: fresh consent is required.
            for path in self.root.iterdir():
                if re.fullmatch(r"[0-9a-f]{32}", path.name):
                    result = self.get(path.name)
                    if result["status"] in ("queued", "running"):
                        result.update(
                            status="failed",
                            error=("Interrupted by application shutdown. "
                                   "Start a new experiment with consent."),
                            updated_at=_now(),
                        )
                        self._save(result)
        finally:
            lease.close()

    def _directory(self, job_id):
        return _safe(self.root / _id(job_id))

    def _save(self, result):
        with _RESULT_LOCK:
            self._write_result(result)

    def _write_result(self, result):
        directory = self._directory(result["id"])
        target = _safe(directory / "result.json")
        raw = json.dumps(result, ensure_ascii=False, allow_nan=False).encode("utf-8")
        if len(raw) > MAX_RESULT_BYTES:
            raise ExperimentError("experiment result exceeds size limit")
        temporary = directory / (".pending-" + uuid.uuid4().hex)
        try:
            with temporary.open("xb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)

    def get(self, job_id):
        with _RESULT_LOCK:
            return self._read_result(job_id)

    def _read_result(self, job_id):
        path = _safe(self._directory(job_id) / "result.json")
        with path.open("rb") as stream:
            raw = stream.read(MAX_RESULT_BYTES + 1)
        try:
            if len(raw) > MAX_RESULT_BYTES:
                raise ValueError()
            data = json.loads(raw, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            allowed = {
                "id",
                "session_id",
                "schema_version",
                "status",
                "created_at",
                "updated_at",
                "consent",
                "limitations",
                "dataset",
                "report",
                "gate_passed",
                "error",
            }
            if not isinstance(data, dict) or data.keys() - allowed:
                raise ValueError()
            if data["id"] != job_id or data["schema_version"] != 1:
                raise ValueError()
            if data["status"] not in ("queued", "running", "completed", "failed"):
                raise ValueError()
            return data
        except (ValueError, KeyError, TypeError):
            raise ExperimentError("stored experiment result is invalid") from None

    def start(self, session_id, *, consent):
        if consent is not True:
            raise ExperimentError("separate explicit consent=true is required for training")
        lease = _Lease(self.root)
        try:
            session = self.store.get(session_id)
            _selected(session)  # Fail before a job or MLflow run exists.
            if not capabilities()["available"]:
                raise ExperimentError(
                    "local ML dependencies are not installed; install the ml extra"
                )
            if sum(p.is_dir() for p in self.root.iterdir()) >= MAX_EXPERIMENTS:
                raise ExperimentError(
                    "experiment limit reached; back up and remove old experiments first"
                )
            timestamp = _now()
            result = {
                "schema_version": 1,
                "id": uuid.uuid4().hex,
                "session_id": session["id"],
                "status": "queued",
                "created_at": timestamp,
                "updated_at": timestamp,
                "consent": {"asserted": True, "asserted_at": timestamp, "statement": CONSENT},
                "limitations": LIMITATIONS,
            }
            self._directory(result["id"]).mkdir(mode=0o700)
            self._save(result)
            thread = threading.Thread(
                target=self._work,
                args=(dict(result), session, lease),
                name="voicefont-experiment",
                daemon=True,
            )
            thread.start()
            return result
        except BaseException:
            lease.close()
            raise

    def _work(self, result, session, lease):
        try:
            result.update(status="running", updated_at=_now())
            self._save(result)
            dataset = session_dataset(self.store, session)
            # Import optional ML only after explicit consent and sufficient recordings.
            from .pipeline import run_pipeline
            from .training import GATE_MARGIN, TrainingConfig, preprocess

            config = TrainingConfig()
            prepared = preprocess(dataset.features, dataset.recording_ids, config)
            result["dataset"] = {
                "feature_version": FEATURE_VERSION,
                "feature_dimensions": int(dataset.features.shape[1]),
                "distinct_recordings": len(dataset.recording_ids),
                "selected_prompts": len(session["accepted"]),
                "train_hashes": sorted(set(prepared.train_groups)),
                "heldout_hashes": sorted(set(prepared.validation_groups)),
                "seed": config.seed,
                "heldout_fraction": config.validation_fraction,
                "maximum_heldout_mse": config.max_validation_mse,
                "baseline_multiplier": GATE_MARGIN,
            }
            report = run_pipeline(
                dataset.features,
                dataset.recording_ids,
                output_dir=self._directory(result["id"]),
                provenance=(
                    f"Authorised calibration session {session['id']}; "
                    f"selected original WAV SHA256 groups; {FEATURE_VERSION}; "
                    "one vector per distinct recording."
                ),
                config=config,
            )
            result.update(
                status="completed",
                report=report,
                gate_passed=report["status"] == "published",
                updated_at=_now(),
            )
            self._save(result)
        except Exception:
            # Never put exception text (which can contain private paths) in HTTP JSON.
            logger.exception("Local experiment %s failed", result["id"])
            result.pop("report", None)
            result.pop("gate_passed", None)
            result.update(
                status="failed",
                error=(
                    "Local experiment failed. Check selected WAV integrity, available disk "
                    "space and local ML setup. No speech model was created."
                ),
                updated_at=_now(),
            )
            try:
                self._save(result)
            except (OSError, ExperimentError):
                logger.warning("Could not persist failed experiment %s", result["id"])
        finally:
            lease.close()
