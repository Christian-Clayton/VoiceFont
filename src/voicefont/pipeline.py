"""Real local LangGraph experiment. Publish means local registry, not deployment."""

import hashlib
import json
import logging
import tempfile
import time
from pathlib import Path
from typing import Any, TypedDict

import numpy as np

from voicefont.tracking import (
    LocalOnlyMLflowConfig,
    LocalOnlyTracking,
    disable_telemetry,
    local_path,
    package_versions,
)
from voicefont.training import (
    DISCLAIMER,
    TrainingConfig,
    evaluate,
    passes_gate,
    preprocess,
    save_model,
    train_autoencoder,
)

disable_telemetry()

from langgraph.graph import END, START, StateGraph  # noqa: E402

logger = logging.getLogger(__name__)


class PipelineState(TypedDict, total=False):
    features: Any
    recording_ids: list[str]
    run_id: str
    provenance: str
    prepared: Any
    model: Any
    metrics: dict[str, float]
    stages: list[str]
    durations: dict[str, float]
    status: str
    model_version: str | None
    dataset_sha256: str


def build_graph(tracking: LocalOnlyTracking, config: TrainingConfig):
    """Compile preprocess -> train -> evaluate -> conditional publish or END."""
    config.validated()

    def timed(stage, action):
        def node(state):
            started = time.perf_counter()
            result = action(state)
            seconds = time.perf_counter() - started
            tracking.log_metrics(state["run_id"], {f"duration_{stage}_s": seconds})
            logger.info("run_id=%s stage=%s duration_s=%.6f", state["run_id"], stage, seconds)
            return {
                **result,
                "stages": [*state.get("stages", []), stage],
                "durations": {**state.get("durations", {}), stage: seconds},
            }

        return node

    def preprocess_node(state):
        prepared = preprocess(state["features"], state["recording_ids"], config)
        digest = hashlib.sha256(np.asarray(state["features"], dtype="<f8").tobytes())
        digest.update(json.dumps(state["recording_ids"], ensure_ascii=True).encode())
        tracking.client.log_param(state["run_id"], "dataset_sha256", digest.hexdigest())
        return {"prepared": prepared, "dataset_sha256": digest.hexdigest()}

    def train_node(state):
        model = train_autoencoder(state["prepared"], config)
        for step, loss in enumerate(model.loss_curve_):
            tracking.log_metrics(state["run_id"], {"training_loss": loss}, step)
        return {"model": model}

    def evaluate_node(state):
        metrics = evaluate(state["model"], state["prepared"])
        tracking.log_metrics(state["run_id"], metrics)
        accepted = passes_gate(metrics, config)
        logger.info("run_id=%s evaluation=%s gate_passed=%s", state["run_id"], metrics, accepted)
        return {"metrics": metrics, "status": "accepted" if accepted else "rejected"}

    def publish_node(state):
        with tempfile.TemporaryDirectory(prefix="voicefont-model-") as directory:
            weights, metadata = save_model(
                state["model"],
                state["prepared"],
                config,
                Path(directory) / "model",
                state["metrics"],
            )
            content = json.loads(metadata.read_text(encoding="utf-8"))
            content.update(
                {
                    "run_id": state["run_id"],
                    "provenance": state["provenance"],
                    "versions": package_versions(),
                    "dataset_sha256": state["dataset_sha256"],
                }
            )
            metadata.write_text(json.dumps(content, indent=2, allow_nan=False), encoding="utf-8")
            tracking.log_artifact(state["run_id"], weights, "model")
            tracking.log_artifact(state["run_id"], metadata, "model")
        model_version = tracking.publish(state["run_id"])
        return {"status": "published", "model_version": model_version}

    graph = StateGraph(PipelineState)
    for stage, action in (
        ("preprocess", preprocess_node),
        ("train", train_node),
        ("evaluate", evaluate_node),
        ("publish", publish_node),
    ):
        graph.add_node(stage, timed(stage, action))
    graph.add_edge(START, "preprocess")
    graph.add_edge("preprocess", "train")
    graph.add_edge("train", "evaluate")
    graph.add_conditional_edges(
        "evaluate", lambda state: state["status"], {"accepted": "publish", "rejected": END}
    )
    graph.add_edge("publish", END)
    return graph.compile()


def run_pipeline(
    features, recording_ids, *, output_dir, provenance: str, config: TrainingConfig | None = None
) -> dict:
    """Run one bounded experiment. Caller supplies original-recording IDs per row.

    Provenance must describe the actual data source. No audio API or downloads.
    Returns a JSON-safe report and logs all stages to local MLflow.
    """
    config = (config or TrainingConfig()).validated()
    if not isinstance(provenance, str) or not 1 <= len(provenance.strip()) <= 1000:
        raise ValueError("provenance must be a nonempty description of at most 1000 characters")
    root = local_path(output_dir)
    tracking = LocalOnlyTracking(LocalOnlyMLflowConfig(root / "mlflow.db", root / "artifacts"))
    run_id = tracking.start_run(config, provenance)
    try:
        state = build_graph(tracking, config).invoke(
            {
                "features": features,
                "recording_ids": list(recording_ids),
                "provenance": provenance,
                "run_id": run_id,
                "model_version": None,
            },
            config={"recursion_limit": 8, "callbacks": []},
        )
        report = {
            key: state[key]
            for key in (
                "run_id",
                "status",
                "model_version",
                "metrics",
                "stages",
                "durations",
                "dataset_sha256",
                "provenance",
            )
        }
        report["disclaimer"] = DISCLAIMER
        tracking.end_run(run_id, report["status"])
        return report
    except Exception:
        tracking.end_run(run_id, "failed", failed=True)
        raise
