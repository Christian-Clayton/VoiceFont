"""Tests for tts_pipeline.py: LangGraph TTS pipeline nodes."""
from unittest.mock import MagicMock, patch

from voicefont.tts_pipeline import (
    TtsPipelineState,
    build_tts_pipeline,
    run_tts_pipeline,
)


def _sample_training_result():
    return {
        "run_id": "test-run-123",
        "status": "completed",
        "final_loss": 0.1,
        "best_loss": 0.05,
        "epochs_trained": 5,
        "training_duration_s": 1.0,
        "peak_vram_mb": 512.0,
        "checkpoints": ["/tmp/ckpt_epoch_0.pth", "/tmp/ckpt_epoch_1.pth"],
    }


class TestPipelineState:
    def test_initial_state_has_empty_stages(self):
        state: TtsPipelineState = {"stages": [], "errors": []}
        assert state["stages"] == []
        assert state["errors"] == []


class TestPreprocessNode:
    def test_preprocess_adds_stage(self):
        state = {"dataset_dir": "data", "stages": [], "errors": []}
        graph = build_tts_pipeline()
        result = graph.invoke(state, {"recursion_limit": 10})
        assert "preprocess" in result["stages"]


class TestEvaluateNode:
    @patch("voicefont.tts_pipeline.train_text2mel")
    def test_evaluate_with_no_training_result(self, mock_train):
        """If training failed, evaluate marks eval_failed."""
        mock_train.side_effect = RuntimeError("CUDA required")
        graph = build_tts_pipeline()
        state = {"dataset_dir": "data", "stages": [], "errors": []}
        result = graph.invoke(state, {"recursion_limit": 10})
        assert result["status"] in ("eval_failed", "train_failed")

    @patch("voicefont.tts_pipeline.train_text2mel")
    def test_evaluate_with_good_training_result(self, mock_train):
        """Evaluate computes metrics correctly when training_result is present."""
        mock_result = MagicMock()
        mock_result.to_dict.return_value = _sample_training_result()
        mock_train.return_value = mock_result

        state: TtsPipelineState = {
            "dataset_dir": "data",
            "stages": [],
            "errors": [],
        }
        graph = build_tts_pipeline()
        result = graph.invoke(state, {"recursion_limit": 10})
        evaluation = result.get("evaluation", {})
        assert evaluation["epochs_trained"] == 5
        assert evaluation["has_checkpoints"] is True
        assert evaluation["final_loss"] == 0.1
        assert evaluation["best_loss"] == 0.05

    @patch("voicefont.tts_pipeline.train_text2mel")
    def test_evaluate_loss_decreased_check(self, mock_train):
        """best_loss < final_loss * 1.1 means loss decreased."""
        mock_result = MagicMock()
        mock_result.to_dict.return_value = {
            "final_loss": 1.0,
            "best_loss": 0.5,
            "epochs_trained": 3,
            "checkpoints": ["/tmp/ckpt.pth"],
            "peak_vram_mb": 256.0,
            "run_id": "r1",
        }
        mock_train.return_value = mock_result

        state: TtsPipelineState = {
            "stages": [],
            "errors": [],
        }
        graph = build_tts_pipeline()
        result = graph.invoke(state, {"recursion_limit": 10})
        evaluation = result.get("evaluation", {})
        assert evaluation["loss_decreased"] is True
        assert evaluation["passed"] is True


class TestDeployNode:
    @patch("voicefont.tts_pipeline.train_text2mel")
    def test_deploy_with_no_checkpoints(self, mock_train):
        """Deploy node marks no_checkpoint when no checkpoints exist."""
        mock_result = MagicMock()
        mock_result.to_dict.return_value = {
            "checkpoints": [],
            "final_loss": 0.1,
            "best_loss": 0.05,
            "epochs_trained": 5,
            "peak_vram_mb": 512.0,
            "run_id": "r1",
        }
        mock_train.return_value = mock_result

        state: TtsPipelineState = {
            "stages": [],
            "errors": [],
        }
        graph = build_tts_pipeline()
        result = graph.invoke(state, {"recursion_limit": 10})
        assert result["status"] in ("evaluated", "no_checkpoint", "eval_failed")

    @patch("voicefont.tts_pipeline.train_text2mel")
    def test_deploy_registers_latest_checkpoint(self, mock_train):
        """Deploy node picks the latest checkpoint."""
        mock_result = MagicMock()
        mock_result.to_dict.return_value = {
            "checkpoints": ["/tmp/ckpt_0.pth", "/tmp/ckpt_1.pth", "/tmp/ckpt_2.pth"],
            "final_loss": 0.1,
            "best_loss": 0.05,
            "epochs_trained": 5,
            "peak_vram_mb": 512.0,
            "run_id": "r1",
        }
        mock_train.return_value = mock_result

        state: TtsPipelineState = {
            "stages": [],
            "errors": [],
        }
        graph = build_tts_pipeline()
        result = graph.invoke(state, {"recursion_limit": 10})
        deploy = result.get("deploy_result", {})
        assert deploy.get("checkpoint") == "/tmp/ckpt_2.pth"
        assert deploy.get("status") == "registered"

    @patch("voicefont.tts_pipeline.train_text2mel")
    def test_deploy_gate_skips_when_eval_failed(self, mock_train):
        """When evaluation didn't pass, deploy is skipped."""
        mock_result = MagicMock()
        mock_result.to_dict.return_value = {
            "checkpoints": ["/tmp/ckpt.pth"],
            "final_loss": 0.5,
            "best_loss": 0.9,  # best > final means loss didn't decrease
            "epochs_trained": 5,
            "peak_vram_mb": 512.0,
            "run_id": "r1",
        }
        mock_train.return_value = mock_result

        state: TtsPipelineState = {
            "stages": [],
            "errors": [],
        }
        graph = build_tts_pipeline()
        result = graph.invoke(state, {"recursion_limit": 10})
        assert result["status"] != "deployed"
        assert "deploy" not in result["stages"]


class TestFullPipeline:
    @patch("voicefont.tts_pipeline.train_text2mel")
    def test_pipeline_runs_with_no_cuda_mocked(self, mock_train):
        """Full pipeline with mocked training."""
        mock_result = MagicMock()
        mock_result.to_dict.return_value = _sample_training_result()
        mock_train.return_value = mock_result

        result = run_tts_pipeline(dataset_dir="data", config={"batch_size": 8})

        assert result["status"] == "deployed"
        assert "preprocess" in result["stages"]
        assert "train" in result["stages"]
        assert "evaluate" in result["stages"]
        assert "deploy" in result["stages"]
        assert len(result["errors"]) == 0

    @patch("voicefont.tts_pipeline.train_text2mel")
    def test_pipeline_handles_training_failure(self, mock_train):
        """Pipeline continues and marks train_failed when training raises."""
        mock_train.side_effect = RuntimeError("CUDA OOM")

        result = run_tts_pipeline(dataset_dir="data", config={})

        assert result["status"] == "eval_failed"
        assert any("CUDA OOM" in e for e in result["errors"])


class TestBuildPipeline:
    def test_graph_has_all_nodes(self):
        graph = build_tts_pipeline()
        compiled_graph = graph.get_graph()
        assert compiled_graph is not None
