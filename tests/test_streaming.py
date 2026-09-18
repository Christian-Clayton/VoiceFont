"""Tests for inference/streaming_engine.py: layer-streamed transformer inference."""
import pytest
import torch
import torch.nn as nn

from voicefont.inference.streaming_engine import DoubleBufferedStreamingModel, StreamingModel


class SimpleTransformer(nn.Module):
    """Minimal transformer for testing streaming."""

    def __init__(self, vocab_size=100, d_model=64, nhead=2, num_layers=4):
        super().__init__()
        self.embedding = nn.Embedding(vocab_size, d_model)
        self.layers = nn.ModuleList([
            nn.TransformerEncoderLayer(d_model, nhead, dim_feedforward=d_model * 4, batch_first=True)
            for _ in range(num_layers)
        ])
        self.norm = nn.LayerNorm(d_model)
        self.head = nn.Linear(d_model, vocab_size)

    def forward(self, x, src_mask=None):
        x = self.embedding(x)
        for layer in self.layers:
            x = layer(x, src_mask=src_mask)
        x = self.norm(x)
        return self.head(x)


@pytest.fixture
def device():
    return torch.device("cuda:0" if torch.cuda.is_available() else "cpu")


@pytest.fixture
def simple_model(device):
    model = SimpleTransformer(vocab_size=100, d_model=64, nhead=2, num_layers=4)
    return model.to(device).eval()


class TestStreamingModel:
    def test_create_streaming_model(self, device):
        model = SimpleTransformer(vocab_size=100, d_model=64, nhead=2, num_layers=4)
        sm = StreamingModel(
            embed_tokens=model.embedding,
            norm=model.norm,
            lm_head=model.head,
            layers=list(model.layers),
            device=device,
            dtype=torch.float32,
        )
        assert sm.num_layers == 4

    def test_forward_shape(self, device):
        model = SimpleTransformer(vocab_size=100, d_model=64, nhead=2, num_layers=4)
        sm = StreamingModel(
            embed_tokens=model.embedding,
            norm=model.norm,
            lm_head=model.head,
            layers=list(model.layers),
            device=device,
            dtype=torch.float32,
        )
        input_ids = torch.randint(0, 100, (1, 16), device=device)
        with torch.no_grad():
            logits = sm(input_ids)
        assert logits.shape == (1, 16, 100)

    def test_forward_matches_standard(self, device):
        """Streaming and standard forward should produce identical outputs."""
        model = SimpleTransformer(vocab_size=100, d_model=64, nhead=2, num_layers=4)
        model = model.to(device).eval()

        # Copy weights to a fresh model for streaming
        model2 = SimpleTransformer(vocab_size=100, d_model=64, nhead=2, num_layers=4)
        model2.load_state_dict(model.state_dict())
        sm = StreamingModel(
            embed_tokens=model2.embedding,
            norm=model2.norm,
            lm_head=model2.head,
            layers=list(model2.layers),
            device=device,
            dtype=torch.float32,
        )

        input_ids = torch.randint(0, 100, (1, 16), device=device)

        with torch.no_grad():
            standard_logits = model(input_ids)
            streaming_logits = sm(input_ids)

        diff = (standard_logits - streaming_logits).abs().max().item()
        assert diff < 1e-4, f"Outputs differ: max diff = {diff}"

    def test_peak_vram_bytes(self, device):
        model = SimpleTransformer(vocab_size=100, d_model=64, nhead=2, num_layers=4)
        sm = StreamingModel(
            embed_tokens=model.embedding,
            norm=model.norm,
            lm_head=model.head,
            layers=list(model.layers),
            device=device,
            dtype=torch.float32,
        )
        peak = sm.peak_vram_bytes()
        total = sm.total_params_bytes()
        assert peak > 0
        assert total > peak  # total includes CPU layers

    def test_resident_fraction(self, device):
        model = SimpleTransformer(vocab_size=100, d_model=64, nhead=2, num_layers=4)
        sm = StreamingModel(
            embed_tokens=model.embedding,
            norm=model.norm,
            lm_head=model.head,
            layers=list(model.layers),
            device=device,
            dtype=torch.float32,
        )
        fraction = sm.resident_fraction()
        assert 0 < fraction < 1  # Not all params resident

    def test_streaming_vram_bounded(self, device):
        """Streaming should use significantly less VRAM than total params."""
        model = SimpleTransformer(vocab_size=100, d_model=64, nhead=2, num_layers=8)
        sm = StreamingModel(
            embed_tokens=model.embedding,
            norm=model.norm,
            lm_head=model.head,
            layers=list(model.layers),
            device=device,
            dtype=torch.float32,
        )
        fraction = sm.resident_fraction()
        # With 8 layers, resident fraction should be well under 50%
        assert fraction < 0.5


class TestDoubleBufferedStreamingModel:
    def test_create(self, device):
        model = SimpleTransformer(vocab_size=100, d_model=64, nhead=2, num_layers=4)
        sm = DoubleBufferedStreamingModel(
            embed_tokens=model.embedding,
            norm=model.norm,
            lm_head=model.head,
            layers=list(model.layers),
            device=device,
            dtype=torch.float32,
        )
        assert sm.num_layers == 4
        assert sm.compute_stream is not None
        assert sm.transfer_stream is not None

    def test_forward_matches_standard(self, device):
        model = SimpleTransformer(vocab_size=100, d_model=64, nhead=2, num_layers=4)
        model = model.to(device).eval()

        model2 = SimpleTransformer(vocab_size=100, d_model=64, nhead=2, num_layers=4)
        model2.load_state_dict(model.state_dict())
        sm = DoubleBufferedStreamingModel(
            embed_tokens=model2.embedding,
            norm=model2.norm,
            lm_head=model2.head,
            layers=list(model2.layers),
            device=device,
            dtype=torch.float32,
        )

        input_ids = torch.randint(0, 100, (1, 16), device=device)

        with torch.no_grad():
            standard_logits = model(input_ids)
            streaming_logits = sm(input_ids)

        diff = (standard_logits - streaming_logits).abs().max().item()
        assert diff < 1e-4, f"Outputs differ: max diff = {diff}"
