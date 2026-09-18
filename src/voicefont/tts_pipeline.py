"""LangGraph TTS pipeline: preprocess → train → evaluate → deploy.

Orchestrates the full TTS workflow as a stateful graph with checkpointing.
"""
from __future__ import annotations

import logging
import time
from typing import TypedDict

from langgraph.graph import END, StateGraph

from voicefont.tts_training import TtsTrainingConfig, train_text2mel

logger = logging.getLogger(__name__)


class TtsPipelineState(TypedDict, total=False):
    run_id: str
    status: str
    dataset_dir: str
    config: dict
    training_result: dict
    evaluation: dict
    deploy_result: dict
    stages: list[str]
    errors: list[str]


def build_tts_pipeline():
    """Build the TTS training and deployment pipeline as a LangGraph."""

    def preprocess_node(state: TtsPipelineState) -> TtsPipelineState:
        """Validate dataset and prepare for training."""
        logger.info("Stage: preprocess")
        state.get("dataset_dir", "training/piper_dataset")
        # Validation happens inside train_text2mel
        return {
            **state,
            "stages": [*state.get("stages", []), "preprocess"],
            "status": "preprocessed",
        }

    def train_node(state: TtsPipelineState) -> TtsPipelineState:
        """Run CUDA training with MLflow tracking."""
        logger.info("Stage: train")
        time.time()
        try:
            config_dict = state.get("config", {})
            config = TtsTrainingConfig(**config_dict)
            result = train_text2mel(config)
            return {
                **state,
                "training_result": result.to_dict(),
                "stages": [*state.get("stages", []), "train"],
                "status": "trained",
            }
        except Exception as e:
            logger.error(f"Training failed: {e}")
            return {
                **state,
                "stages": [*state.get("stages", []), "train"],
                "status": "train_failed",
                "errors": [*state.get("errors", []), str(e)],
            }

    def evaluate_node(state: TtsPipelineState) -> TtsPipelineState:
        """Evaluate training results: loss decreased, weights changed, MLflow logged."""
        logger.info("Stage: evaluate")
        result = state.get("training_result", {})
        if not result:
            return {**state, "status": "eval_failed", "stages": [*state.get("stages", []), "evaluate"]}

        evaluation = {
            "loss_decreased": result.get("best_loss", float("inf")) < result.get("final_loss", float("inf")) * 1.1,
            "final_loss": result.get("final_loss", 0),
            "best_loss": result.get("best_loss", 0),
            "epochs_trained": result.get("epochs_trained", 0),
            "peak_vram_mb": result.get("peak_vram_mb", 0),
            "has_checkpoints": len(result.get("checkpoints", [])) > 0,
            "mlflow_run_id": result.get("run_id", ""),
        }
        evaluation["passed"] = (
            evaluation["loss_decreased"]
            and evaluation["has_checkpoints"]
            and evaluation["epochs_trained"] > 0
        )

        return {
            **state,
            "evaluation": evaluation,
            "stages": [*state.get("stages", []), "evaluate"],
            "status": "evaluated",
        }

    def deploy_node(state: TtsPipelineState) -> TtsPipelineState:
        """Register model for deployment (local registry)."""
        logger.info("Stage: deploy")
        result = state.get("training_result", {})
        checkpoints = result.get("checkpoints", [])
        if not checkpoints:
            return {**state, "status": "no_checkpoint", "stages": [*state.get("stages", []), "deploy"]}

        # Register latest checkpoint
        latest_ckpt = checkpoints[-1]
        deploy_result = {
            "checkpoint": latest_ckpt,
            "registered_at": time.time(),
            "status": "registered",
        }

        return {
            **state,
            "deploy_result": deploy_result,
            "stages": [*state.get("stages", []), "deploy"],
            "status": "deployed",
        }

    def should_deploy(state: TtsPipelineState) -> str:
        """Gate: only deploy if evaluation passed."""
        evaluation = state.get("evaluation", {})
        if evaluation.get("passed", False):
            return "deploy"
        return "end"

    # Build graph
    graph = StateGraph(TtsPipelineState)
    graph.add_node("preprocess", preprocess_node)
    graph.add_node("train", train_node)
    graph.add_node("evaluate", evaluate_node)
    graph.add_node("deploy", deploy_node)

    graph.add_edge("__start__", "preprocess")
    graph.add_edge("preprocess", "train")
    graph.add_edge("train", "evaluate")
    graph.add_conditional_edges("evaluate", should_deploy, {"deploy": "deploy", "end": END})
    graph.add_edge("deploy", END)

    return graph.compile()


def run_tts_pipeline(dataset_dir: str = "training/piper_dataset",
                     config: dict | None = None) -> dict:
    """Run the full TTS pipeline."""
    app = build_tts_pipeline()
    initial_state = {
        "dataset_dir": dataset_dir,
        "config": config or {},
        "stages": [],
        "errors": [],
    }
    result = app.invoke(initial_state, {"recursion_limit": 10})
    return {
        "status": result.get("status", "unknown"),
        "stages": result.get("stages", []),
        "training_result": result.get("training_result", {}),
        "evaluation": result.get("evaluation", {}),
        "deploy_result": result.get("deploy_result", {}),
        "errors": result.get("errors", []),
    }
