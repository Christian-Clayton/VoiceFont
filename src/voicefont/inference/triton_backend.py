"""Triton Inference Server Python backend with layer streaming.

Wraps the StreamingModel for production inference via Triton's protocol.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import numpy as np
import torch

logger = logging.getLogger(__name__)

# Check if Triton backend is available
try:
    import triton_python_backend_utils as pb_utils
    TRITON_AVAILABLE = True
except ImportError:
    TRITON_AVAILABLE = False
    logger.warning("Triton backend utils not available. Running in standalone mode.")


class StreamingInferenceBackend:
    """Triton Python backend for layer-streamed transformer inference."""

    def __init__(self):
        self.model = None
        self.config = None
        self.device = None

    def initialize(self, args: dict) -> None:
        """Initialize the model. Called once when Triton loads the backend."""
        json.loads(args["model_config"])

        # Load config from model directory
        model_instance_name = args.get("model_instance_name", "streaming_model")
        model_repository = args.get("model_repository", "")

        # Get model path from config or environment
        model_path = os.environ.get(
            "STREAMING_MODEL_PATH",
            str(Path(model_repository) / model_instance_name / "model"),
        )

        # Get dtype from config
        dtype_str = os.environ.get("STREAMING_DTYPE", "fp16")
        dtype = torch.float16 if dtype_str == "fp16" else torch.bfloat16 if dtype_str == "bf16" else torch.float32

        # Get number of buffers
        num_buffers = int(os.environ.get("STREAMING_BUFFERS", "2"))

        # Get device
        device_str = os.environ.get("STREAMING_DEVICE", "cuda:0")
        self.device = torch.device(device_str) if torch.cuda.is_available() else torch.device("cpu")

        logger.info(f"Initializing streaming backend for model: {model_path}")
        logger.info(f"Device: {self.device}, dtype: {dtype}, buffers: {num_buffers}")

        # Load streaming model
        from voicefont.inference.streaming_engine import StreamingModel
        self.model = StreamingModel.from_pretrained(
            model_path,
            device=self.device,
            dtype=dtype,
        )

        logger.info(f"Model loaded: {self.model.num_layers} layers")
        logger.info(f"Peak VRAM: {self.model.peak_vram_bytes() / 1024**3:.2f} GB")
        logger.info(f"Total params: {self.model.total_params_bytes() / 1024**3:.2f} GB")
        logger.info(f"Resident fraction: {self.model.resident_fraction():.2%}")

    def execute(self, requests: list) -> list:
        """Process inference requests. Called for each batch of requests."""
        responses = []

        for request in requests:
            # Parse input
            if TRITON_AVAILABLE:
                input_ids_tensor = pb_utils.get_input_tensor_by_name(request, "input_ids")
                input_ids = torch.from_numpy(input_ids_tensor.as_numpy()).to(self.device)

                # Optional attention mask
                try:
                    attention_mask_tensor = pb_utils.get_input_tensor_by_name(request, "attention_mask")
                    attention_mask = torch.from_numpy(attention_mask_tensor.as_numpy()).to(self.device)
                except Exception:
                    attention_mask = None
            else:
                # Standalone mode
                input_ids = request.get("input_ids")
                attention_mask = request.get("attention_mask")

            # Run inference
            with torch.no_grad():
                logits = self.model(
                    input_ids=input_ids,
                    attention_mask=attention_mask,
                )

            # Return response
            if TRITON_AVAILABLE:
                logits_tensor = pb_utils.Tensor(
                    "logits",
                    logits.cpu().numpy().astype(np.float32),
                )
                response = pb_utils.InferenceResponse(output_tensors=[logits_tensor])
                responses.append(response)
            else:
                responses.append({"logits": logits.cpu().numpy()})

        return responses

    def finalize(self) -> None:
        """Clean up. Called when Triton shuts down the backend."""
        logger.info("Finalizing streaming backend")
        self.model = None


# Triton Python Backend entry point (class name must be TritonPythonModel)
class TritonPythonModel(StreamingInferenceBackend):
    """Triton Python backend wrapper.

    Triton Inference Server expects a class named TritonPythonModel
    with initialize(), execute(), and finalize() methods.
    """
    pass


# Standalone entry point for testing without Triton
def run_standalone(
    model_path: str,
    input_ids: np.ndarray,
    attention_mask: np.ndarray | None = None,
    device: str = "cuda:0",
    dtype: str = "fp16",
    num_buffers: int = 2,
) -> np.ndarray:
    """Run inference without Triton (for testing)."""
    backend = StreamingInferenceBackend()

    args = {
        "model_config": json.dumps({}),
        "model_repository": str(Path(model_path).parent),
        "model_instance_name": Path(model_path).name,
    }
    os.environ["STREAMING_MODEL_PATH"] = model_path
    os.environ["STREAMING_DTYPE"] = dtype
    os.environ["STREAMING_BUFFERS"] = str(num_buffers)
    os.environ["STREAMING_DEVICE"] = device

    backend.initialize(args)

    request = {
        "input_ids": torch.from_numpy(input_ids),
        "attention_mask": torch.from_numpy(attention_mask) if attention_mask is not None else None,
    }
    responses = backend.execute([request])
    return responses[0]["logits"]
