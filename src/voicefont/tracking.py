"""Local-only MLflow adapter. Import this before LangGraph or MLflow.

No autologging, remote tracking, cloud registry or telemetry integrations.
"""

import json
import os
import re
from dataclasses import asdict, dataclass
from importlib.metadata import version
from pathlib import Path
from urllib.parse import unquote, urlsplit


def disable_telemetry() -> None:
    """Override inherited opt-ins before third-party imports and on each run."""
    for key, value in {
        "MLFLOW_DISABLE_TELEMETRY": "true",
        "MLFLOW_ENABLE_SYSTEM_METRICS_LOGGING": "false",
        "MLFLOW_ENABLE_ASYNC_LOGGING": "false",
        "LANGSMITH_TRACING": "false",
        "LANGCHAIN_TRACING_V2": "false",
        "LANGCHAIN_TRACING": "false",
        "OTEL_SDK_DISABLED": "true",
    }.items():
        os.environ[key] = value


disable_telemetry()


def local_path(value) -> Path:
    """Accept local paths/file URIs only; reject network shares and URI schemes."""
    raw = str(value).replace("\\", "/")
    if raw.startswith("file:"):
        parsed = urlsplit(raw)
        if parsed.netloc or parsed.query or parsed.fragment:
            raise ValueError("only local filesystem paths are allowed")
        raw = unquote(parsed.path)
        if os.name == "nt" and re.match(r"^/[A-Za-z]:/", raw):
            raw = raw[1:]
    if raw.startswith("//") or (":" in raw and not re.match(r"^[A-Za-z]:/", raw)):
        raise ValueError("only local filesystem paths are allowed")
    resolved = Path(raw).resolve()
    if resolved.as_posix().startswith("//"):
        raise ValueError("only local filesystem paths are allowed")
    return resolved


def ensure_local_only() -> None:
    disable_telemetry()
    for name in ("MLFLOW_TRACKING_URI", "MLFLOW_REGISTRY_URI"):
        uri = os.environ.get(name, "")
        if not uri:
            continue
        if uri in ("databricks", "databricks-uc"):
            raise ValueError("only local MLflow stores are allowed")
        if uri.startswith("sqlite:///"):
            path = uri[len("sqlite:///") :]
            if "?" in path or "#" in path:
                raise ValueError("only plain local SQLite paths are allowed")
            local_path(path)
        elif uri.startswith("sqlite:"):
            raise ValueError("only local SQLite stores are allowed")
        else:
            local_path(uri)


def package_versions() -> dict[str, str]:
    return {name: version(name) for name in ("numpy", "scikit-learn", "langgraph", "mlflow")}


@dataclass(frozen=True)
class LocalOnlyMLflowConfig:
    db_path: Path
    artifact_root: Path

    def __post_init__(self):
        object.__setattr__(self, "db_path", local_path(self.db_path))
        object.__setattr__(self, "artifact_root", local_path(self.artifact_root))

    @property
    def tracking_uri(self) -> str:
        return "sqlite:///" + self.db_path.as_posix()


class LocalOnlyTracking:
    """Use explicit clients and run IDs, never MLflow's process-global active run."""

    def __init__(self, config: LocalOnlyMLflowConfig):
        ensure_local_only()
        from mlflow.tracking import MlflowClient

        self.config = config
        config.db_path.parent.mkdir(parents=True, exist_ok=True)
        config.artifact_root.mkdir(parents=True, exist_ok=True)
        self.client = MlflowClient(
            tracking_uri=config.tracking_uri, registry_uri=config.tracking_uri
        )

    def ensure_experiment(self, name: str) -> str:
        experiment = self.client.get_experiment_by_name(name)
        if experiment is None:
            experiment_id = self.client.create_experiment(
                name, artifact_location=self.config.artifact_root.as_uri()
            )
            experiment = self.client.get_experiment(experiment_id)
        artifact_path = local_path(experiment.artifact_location)
        if artifact_path != self.config.artifact_root:
            raise ValueError("experiment must use the configured local artifact root")
        return experiment.experiment_id

    def start_run(self, config, provenance: str) -> str:
        experiment_id = self.ensure_experiment("voicefont-numeric-autoencoder")
        run = self.client.create_run(
            experiment_id,
            tags={
                "disposition": "running",
                "purpose": "numeric feature reconstruction only",
                "provenance": provenance,
            },
        )
        run_id = run.info.run_id
        for key, value in asdict(config).items():
            self.client.log_param(run_id, key, value)
        self.client.log_param(run_id, "versions", json.dumps(package_versions(), sort_keys=True))
        return run_id

    def log_metrics(self, run_id: str, metrics: dict, step: int = 0) -> None:
        for name, value in metrics.items():
            self.client.log_metric(run_id, name, float(value), step=step)

    def log_artifact(self, run_id: str, path, artifact_path: str) -> None:
        run = self.client.get_run(run_id)
        root = local_path(run.info.artifact_uri)
        if not root.is_relative_to(self.config.artifact_root):
            raise ValueError("run must use the configured local artifact root")
        self.client.log_artifact(run_id, str(local_path(path)), artifact_path)

    def publish(self, run_id: str) -> str:
        """Register safe local artifacts, not deployment or a serving endpoint."""
        name = "voicefont-numeric-autoencoder"
        if not self.client.search_registered_models(filter_string=f"name='{name}'"):
            self.client.create_registered_model(name)
        run = self.client.get_run(run_id)
        source = local_path(run.info.artifact_uri) / "model"
        if not source.is_relative_to(self.config.artifact_root):
            raise ValueError("model must use the configured local artifact root")
        result = self.client.create_model_version(name, source.as_uri(), run_id=run_id)
        return result.version

    def end_run(self, run_id: str, disposition: str, failed: bool = False) -> None:
        self.client.set_tag(run_id, "disposition", disposition)
        self.client.set_terminated(run_id, status="FAILED" if failed else "FINISHED")
