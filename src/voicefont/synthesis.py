"""Offline process-isolated speech, bounded single-worker jobs, no user-data logs.

Configuration and the local disk are owner-trusted. HTTP callers cannot select
executables, model paths, output paths or fixture mode. Jobs are session-local.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import subprocess
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from .audio import MAX_FILE_BYTES, read_audio
from .registry import ProfileStore, RegistryError, validate_voice_id

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_SHA256 = "d0f5806f6e034e660c46a0b2fe4c597f0a1670859743c14e27a8823a7d169263"
TERMINAL = {"completed", "failed", "cancelled"}


class SynthesisError(ValueError):
    def __init__(self, message: str, status_code: int = 422):
        super().__init__(message)
        self.status_code = status_code


def default_config_path() -> Path:
    return Path(
        os.environ.get(
            "VOICEFONT_OPENVOICE_CONFIG", REPO_ROOT / "data/openvoice-runtime/config.json"
        )
    )


def load_runtime_config(path: str | Path | None = None) -> dict:
    config = json.loads(Path(path or default_config_path()).read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError("runtime configuration must be an object")
    if config.get("schema_version") != 1 or config.get("device") != "cpu":
        raise ValueError("unsupported runtime configuration")
    for key in ("python", "runtime_root", "worker"):
        item = Path(config[key])
        if not item.is_absolute() or not item.exists():
            raise ValueError("missing configured runtime resource")
    root = Path(config["runtime_root"])
    manifest = json.loads((root / "runtime-manifest.json").read_text(encoding="utf-8"))
    if not manifest.get("files"):
        raise ValueError("missing manifest")
    for item in manifest["files"]:
        resource = root / item["path"]
        if not resource.resolve().is_relative_to(root.resolve()):
            raise ValueError("invalid resource path")
        if not resource.is_file() or resource.stat().st_size != item["size"]:
            raise ValueError("missing or incomplete resource")
    config["timeout_seconds"] = float(config.get("timeout_seconds", 180))
    if not 1 <= config["timeout_seconds"] <= 300:
        raise ValueError("invalid timeout")
    return config


def synthesis_capabilities(config_path: str | Path | None = None) -> dict:
    try:
        load_runtime_config(config_path)
    except (OSError, ValueError, KeyError, TypeError):
        return dict(
            available=False,
            backend="openvoice-v2",
            device="cpu",
            message="Offline OpenVoice runtime is not provisioned or is incomplete.",
        )
    return dict(
        available=True,
        backend="openvoice-v2",
        device="cpu",
        message="Offline English synthesis configured. Neutral style only; CPU may be slow.",
    )


# Short alias for parent API health integration.
capabilities = synthesis_capabilities


def _terminate_tree(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        # /T includes descendants, /F prevents a hung neural worker from surviving cancellation.
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
            check=False,
        )
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    if process.poll() is None:
        process.kill()
    process.wait(timeout=10)


class OpenVoiceBackend:
    def __init__(self, config_path: str | Path | None = None):
        self.config_path = Path(config_path or default_config_path())

    def capability(self):
        return synthesis_capabilities(self.config_path)

    def run(
        self, reference: Path, text: str, speed: float, output: Path, cancel: threading.Event
    ) -> None:
        config = load_runtime_config(self.config_path)
        payload = dict(
            runtime_root=config["runtime_root"],
            reference=str(reference),
            text=text,
            speed=speed,
            output=str(output),
        )
        env = dict(
            os.environ,
            HF_HUB_OFFLINE="1",
            TRANSFORMERS_OFFLINE="1",
            HF_HUB_DISABLE_TELEMETRY="1",
            DO_NOT_TRACK="1",
            PYTHONUTF8="1",
        )
        # Never place text/reference in argv, shell strings, stdout, stderr or durable logs.
        kwargs = (
            {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
            if os.name == "nt"
            else {"start_new_session": True}
        )
        process = subprocess.Popen(
            [config["python"], config["worker"]],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
            cwd=config["runtime_root"],
            **kwargs,
        )
        deadline = time.monotonic() + config["timeout_seconds"]
        try:
            assert process.stdin is not None
            process.stdin.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
            process.stdin.close()
            while process.poll() is None:
                if cancel.wait(0.05):
                    _terminate_tree(process)
                    return
                if time.monotonic() > deadline:
                    _terminate_tree(process)
                    raise SynthesisError("Speech generation timed out.", 504)
            if process.returncode != 0:
                raise SynthesisError("Speech generation failed.", 500)
        finally:
            _terminate_tree(process)
            if process.stdin is not None:
                process.stdin.close()


@dataclass
class _Job:
    id: str
    directory: Path
    text: str
    speed: float
    voice_id: str | None
    fixture: Path | None = None
    status: str = "queued"
    error: str | None = None
    tone: dict | None = None
    cancel: threading.Event = field(default_factory=threading.Event)
    done: threading.Event = field(default_factory=threading.Event)

    def public(self) -> dict:
        value = dict(id=self.id, status=self.status)
        if self.error:
            value["error"] = self.error
        if self.status == "completed":
            value["audio_url"] = f"/synthesis/jobs/{self.id}/audio"
            # Tone describes the delivered speech; failures stay minimal and generic.
            if self.tone is not None:
                value["tone"] = self.tone
        return value


class SynthesisService:
    """At most queue_limit outstanding jobs (including the one running).

    Retain up to 100 terminal results per service lifetime. Shutdown cancels work,
    joins the coordinator and removes every private reference and generated file.
    """

    def __init__(
        self, profile_root: str | Path, *, config_path=None, backend=None, queue_limit: int = 4
    ):
        if type(queue_limit) is not int or not 1 <= queue_limit <= 4:
            raise ValueError("queue_limit must be 1-4")
        self.store = ProfileStore(profile_root)
        self.backend = backend if backend is not None else OpenVoiceBackend(config_path)
        self.queue_limit = queue_limit
        self.output_root = Path(tempfile.mkdtemp(prefix="voicefont-synthesis-"))
        self._condition = threading.Condition(threading.RLock())
        self._jobs: dict[str, _Job] = {}
        self.closed = False
        self._unavailable: str | None = None
        self._thread: threading.Thread | None = None

    def capability(self) -> dict:
        capability = self.backend.capability()
        with self._condition:
            if self._unavailable:
                return {**capability, "available": False, "message": self._unavailable}
        return capability

    @staticmethod
    def analyze(text: str) -> dict:
        """Deterministic tone analysis of text; no synthesis and no network."""
        from .tone import analyze

        return analyze(text)

    @staticmethod
    def _validate(text, style, speed):
        if not isinstance(text, str) or not 1 <= len(text.strip()) or len(text) > 1000:
            raise SynthesisError("text must contain 1-1000 characters")
        if style != "neutral":
            raise SynthesisError("Only neutral style is supported.")
        if (
            isinstance(speed, bool)
            or not isinstance(speed, (float, int))
            or not 0.75 <= speed <= 1.5
        ):
            raise SynthesisError("speed must be between 0.75 and 1.5")

    def _reference(self, voice_id: str) -> Path:
        try:
            profile = self.store.get(validate_voice_id(voice_id))
        except FileNotFoundError:
            raise SynthesisError("profile not found", 404) from None
        except (RegistryError, ValueError, OSError):
            raise SynthesisError("Profile consent or reference validation failed.") from None
        return self.store.root / profile.voice_id / profile.references[0].path

    def submit(
        self, *, voice_id: str, text: str, style: str = "neutral", speed: float = 1.0
    ) -> dict:
        self._validate(text, style, speed)
        if not self.capability()["available"]:
            raise SynthesisError(
                "Offline synthesis is unavailable. Provision the runtime first.", 503
            )
        self._reference(voice_id)  # Consent and integrity before accepting any work.
        return self._enqueue(text, speed, voice_id)

    def submit_technical_fixture(self, *, text: str, speed: float = 1.0) -> dict:
        """Developer-only service test. Never exposed via router, never enrolls a voice.

        This official reference has repository provenance, not a verified speaker release.
        """
        self._validate(text, "neutral", speed)
        if not isinstance(self.backend, OpenVoiceBackend):
            raise SynthesisError("Fixture mode requires the genuine backend.")
        config = load_runtime_config(self.backend.config_path)
        fixture = Path(config["runtime_root"]) / "OpenVoice/resources/example_reference.mp3"
        if hashlib.sha256(fixture.read_bytes()).hexdigest() != FIXTURE_SHA256:
            raise SynthesisError("Technical fixture integrity check failed.")
        return self._enqueue(text, speed, None, fixture)

    def _enqueue(self, text, speed, voice_id, fixture=None):
        with self._condition:
            if self.closed:
                raise SynthesisError("Speech service is shutting down.", 503)
            if self._thread is not None and not self._thread.is_alive():
                self._degrade("Speech coordinator stopped. Restart the service.")
            if self._unavailable:
                raise SynthesisError(self._unavailable, 503)
            if sum(j.status not in TERMINAL for j in self._jobs.values()) >= self.queue_limit:
                raise SynthesisError("Speech queue is full. Try again after a job finishes.", 429)
            terminal = [j for j in self._jobs.values() if j.status in TERMINAL]
            for old in terminal[: max(0, len(self._jobs) - 99)]:
                shutil.rmtree(old.directory, ignore_errors=True)
                del self._jobs[old.id]
            job_id = str(uuid.uuid4())
            directory = self.output_root / job_id
            directory.mkdir()
            from .tone import analyze

            job = _Job(job_id, directory, text, speed, voice_id, fixture)
            job.tone = analyze(text)
            self._jobs[job_id] = job
            if self._thread is None:
                self._thread = threading.Thread(
                    target=self._work, name="voicefont-speech", daemon=True
                )
                self._thread.start()
            self._condition.notify_all()
            return job.public()

    def _lookup(self, job_id):
        try:
            if str(uuid.UUID(job_id)) != job_id:
                raise ValueError
            return self._jobs[job_id]
        except (ValueError, AttributeError, KeyError):
            raise SynthesisError("Speech job not found.", 404) from None

    def get(self, job_id: str) -> dict:
        with self._condition:
            return self._lookup(job_id).public()

    def wait(self, job_id: str, timeout: float = 190) -> dict:
        with self._condition:
            job = self._lookup(job_id)
        if not job.done.wait(timeout):
            raise SynthesisError("Speech job is still running.", 504)
        return self.get(job_id)

    def cancel(self, job_id: str) -> dict:
        with self._condition:
            job = self._lookup(job_id)
            if job.status in TERMINAL:
                return job.public()
            job.cancel.set()
            if job.status == "queued":
                job.text = ""
                job.status = "cancelled"
                shutil.rmtree(job.directory, ignore_errors=True)
                job.done.set()
            self._condition.notify_all()
        # A cancelled response means compute has actually stopped, not just requested.
        if not job.done.wait(25):
            raise SynthesisError("Cancellation is still in progress.", 503)
        return self.get(job_id)

    def audio(self, job_id: str) -> bytes:
        with self._condition:
            job = self._lookup(job_id)
            if job.status != "completed":
                raise SynthesisError("Speech audio is not ready.", 409)
            return (job.directory / "speech.wav").read_bytes()

    def _degrade(self, message: str):
        """Called under the condition; retain directories for shutdown cleanup."""
        self._unavailable = message
        for pending in self._jobs.values():
            if pending.status not in TERMINAL:
                pending.cancel.set()
                pending.text = ""
                pending.status = "failed"
                pending.error = message
                pending.done.set()
        self._condition.notify_all()

    @staticmethod
    def _remove_directory(directory: Path):
        try:
            shutil.rmtree(directory)
        except FileNotFoundError:
            if directory.exists():
                raise

    def _finish(self, job: _Job, status: str, error: str | None = None):
        """Publish terminal state only after cleanup; always release waiters.

        On cleanup failure discard audio and retry whole-directory removal once.
        Persistent faults stop new work; close() retries removal after workers stop.
        """
        try:
            try:
                if status == "completed":
                    for path in job.directory.iterdir():
                        if path.name != "speech.wav":
                            if path.is_dir():
                                shutil.rmtree(path)
                            else:
                                path.unlink()
                else:
                    self._remove_directory(job.directory)
            except OSError:
                status = "failed"
                error = "Speech temporary-file cleanup failed."
                try:
                    self._remove_directory(job.directory)
                except OSError:
                    self._degrade(
                        "Speech cleanup is incomplete. Restart the service after releasing files."
                    )
        finally:
            job.text = ""
            job.status = status
            job.error = error if status == "failed" else None
            job.done.set()
            self._condition.notify_all()

    def _work(self):
        try:
            self._work_loop()
        except Exception:
            # No exception details: they may contain reference paths or speech text.
            with self._condition:
                self._degrade("Speech coordinator stopped. Restart the service.")
        finally:
            with self._condition:
                if not self.closed and not self._unavailable:
                    self._degrade("Speech coordinator stopped. Restart the service.")

    def _work_loop(self):
        while True:
            with self._condition:
                self._condition.wait_for(
                    lambda: (
                        self.closed
                        or self._unavailable
                        or any(j.status == "queued" for j in self._jobs.values())
                    )
                )
                if self.closed or self._unavailable:
                    return
                job = next(j for j in self._jobs.values() if j.status == "queued")
                job.status = "running"
            error = None
            try:
                # Revalidate queued consent before execution and use a private byte snapshot.
                reference = job.fixture or self._reference(job.voice_id)
                local_reference = job.directory / ("reference" + reference.suffix)
                with reference.open("rb") as stream:
                    raw = stream.read(MAX_FILE_BYTES + 1)
                if len(raw) > MAX_FILE_BYTES:
                    raise SynthesisError("Invalid reference.")
                local_reference.write_bytes(raw)
                if not job.cancel.is_set():
                    self.backend.run(
                        local_reference,
                        job.text,
                        job.speed,
                        job.directory / "speech.wav",
                        job.cancel,
                    )
                if not job.cancel.is_set():
                    # Reject missing, malformed, oversized or silent subprocess output.
                    audio = read_audio(job.directory / "speech.wav")
                    if not audio.samples.any():
                        raise SynthesisError("Speech generation failed.", 500)
            except SynthesisError as exc:
                error = (
                    "Speech generation timed out."
                    if exc.status_code == 504
                    else "Speech generation failed."
                )
            except Exception:
                error = "Speech generation failed."
            finally:
                with self._condition:
                    self._finish(
                        job,
                        "cancelled"
                        if job.cancel.is_set()
                        else ("failed" if error else "completed"),
                        error,
                    )

    def close(self):
        with self._condition:
            # Repeated close() retries cleanup after an owner releases locked files.
            self.closed = True
            for job in self._jobs.values():
                if job.status not in TERMINAL:
                    job.cancel.set()
                    if job.status == "queued":
                        job.status = "cancelled"
                        job.text = ""
                        job.done.set()
            self._condition.notify_all()
        if self._thread is not None:
            self._thread.join(timeout=30)
            if self._thread.is_alive():
                raise RuntimeError("Speech worker did not stop")
        try:
            self._remove_directory(self.output_root)
        except OSError:
            with self._condition:
                self._degrade("Speech shutdown cleanup is incomplete.")
            raise RuntimeError("Speech shutdown cleanup is incomplete.") from None
