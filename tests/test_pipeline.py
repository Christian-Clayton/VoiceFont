"""Integration tests use a real compiled graph, SQLite and filesystem artifacts."""

import json
import os

import numpy as np
import pytest

from voicefont.pipeline import build_graph, run_pipeline
from voicefont.tracking import LocalOnlyMLflowConfig, LocalOnlyTracking
from voicefont.training import TrainingConfig


def synthetic_fixture():
    rng = np.random.default_rng(7)
    latent = rng.normal(size=(160, 1))
    features = latent @ np.array([[1.0, -2.0, 0.5, 3.0]])
    features += rng.normal(scale=0.01, size=features.shape)
    return features, [f"synthetic-{i // 4}" for i in range(160)]


def test_real_graph_publishes_local_safe_artifacts_and_mlflow_metrics(tmp_path):
    features, groups = synthetic_fixture()
    tracking = LocalOnlyTracking(
        LocalOnlyMLflowConfig(tmp_path / "mlflow.db", tmp_path / "artifacts")
    )
    graph = build_graph(tracking, TrainingConfig(bottleneck=1))
    assert {"preprocess", "train", "evaluate", "publish"} <= set(graph.get_graph().nodes)
    report = run_pipeline(
        features,
        groups,
        output_dir=tmp_path,
        config=TrainingConfig(bottleneck=1),
        provenance="synthetic smoke fixture, no voice quality claims",
    )
    assert report["status"] == "published"
    assert report["stages"] == ["preprocess", "train", "evaluate", "publish"]
    run = tracking.client.get_run(report["run_id"])
    assert run.info.status == "FINISHED"
    assert run.data.tags["disposition"] == "published"
    assert run.data.params["seed"] == "7"
    assert run.data.metrics["validation_mse"] < run.data.metrics["baseline_mse"] * 0.1
    for stage in report["stages"]:
        assert run.data.metrics[f"duration_{stage}_s"] >= 0
    assert tracking.client.get_metric_history(report["run_id"], "training_loss")
    assert run.info.artifact_uri.startswith(tmp_path.as_uri())
    artifacts = tracking.client.list_artifacts(report["run_id"], "model")
    assert {a.path for a in artifacts} == {"model/model.npz", "model/model.json"}
    weights = tracking.client.download_artifacts(report["run_id"], "model/model.npz")
    with np.load(weights, allow_pickle=False) as data:
        assert data["w0"].shape == (4, 1)
    meta = tracking.client.download_artifacts(report["run_id"], "model/model.json")
    metadata = json.loads(open(meta, encoding="utf-8").read())
    assert metadata["provenance"].startswith("synthetic")
    assert metadata["versions"]["mlflow"]
    assert metadata["run_id"] == report["run_id"]
    assert tracking.client.search_model_versions(f"run_id='{report['run_id']}'")
    assert os.environ["MLFLOW_DISABLE_TELEMETRY"] == "true"
    assert os.environ["LANGSMITH_TRACING"] == "false"


def test_failed_gate_stops_before_publish_and_has_no_model_artifact(tmp_path):
    features, groups = synthetic_fixture()
    report = run_pipeline(
        features,
        groups,
        output_dir=tmp_path,
        config=TrainingConfig(bottleneck=1, max_validation_mse=0.0),
        provenance="synthetic smoke fixture",
    )
    assert report["status"] == "rejected"
    assert report["stages"] == ["preprocess", "train", "evaluate"]
    assert report["model_version"] is None
    tracking = LocalOnlyTracking(
        LocalOnlyMLflowConfig(tmp_path / "mlflow.db", tmp_path / "artifacts")
    )
    assert not tracking.client.list_artifacts(report["run_id"], "model")
    assert not tracking.client.search_model_versions(f"run_id='{report['run_id']}'")
    assert not (tmp_path / "published").exists()


@pytest.mark.parametrize(
    "uri",
    [
        "https://example.com",
        "sqlite://remote/db",
        "s3://bucket",
        "databricks",
        "file://server/share",
    ],
)
def test_refuses_remote_environment_tracking_uri(tmp_path, monkeypatch, uri):
    monkeypatch.setenv("MLFLOW_TRACKING_URI", uri)
    with pytest.raises(ValueError, match="local"):
        LocalOnlyTracking(LocalOnlyMLflowConfig(tmp_path / "mlflow.db", tmp_path / "artifacts"))


@pytest.mark.parametrize("remote", ["s3://bucket/models", "https://host/store", "//host/share"])
def test_refuses_remote_artifact_paths(tmp_path, remote):
    with pytest.raises(ValueError, match="local"):
        LocalOnlyMLflowConfig(tmp_path / "mlflow.db", remote)


def test_refuses_remote_existing_experiment_artifact_store(tmp_path):
    tracking = LocalOnlyTracking(
        LocalOnlyMLflowConfig(tmp_path / "mlflow.db", tmp_path / "artifacts")
    )
    tracking.client.create_experiment("bad-store", artifact_location="s3://bucket/models")
    with pytest.raises(ValueError, match="local"):
        tracking.ensure_experiment("bad-store")
