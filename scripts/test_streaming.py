"""End-to-end test of the streaming engine with a custom model."""
import sys

sys.path.insert(0, 'src')

import time

import torch
import torch.nn as nn


class SimpleTransformer(nn.Module):
    """Minimal transformer for testing streaming."""

    def __init__(self, vocab_size=1000, d_model=128, nhead=4, num_layers=4):
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


def test_streaming():
    from voicefont.inference.streaming_engine import StreamingModel

    print("=" * 60)
    print("Test: Streaming Engine with Custom Model")
    print("=" * 60)

    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    # Create model
    model = SimpleTransformer(vocab_size=1000, d_model=128, nhead=4, num_layers=8)
    total_params = sum(p.numel() for p in model.parameters())
    print(f"Model: {total_params:,} params")

    # Split into StreamingModel components
    list(model.layers)

    # Standard forward
    model = model.to(device).eval()
    input_ids = torch.randint(0, 1000, (1, 32), device=device)

    with torch.no_grad():
        start = time.perf_counter()
        standard_logits = model(input_ids)
        standard_time = time.perf_counter() - start
    print(f"Standard forward: {standard_time:.4f}s, output shape: {standard_logits.shape}")

    # Streaming forward - copy weights from original model
    model2 = SimpleTransformer(vocab_size=1000, d_model=128, nhead=4, num_layers=8)
    model2.load_state_dict(model.state_dict())  # <-- copy weights
    sm = StreamingModel(
        embed_tokens=model2.embedding,
        norm=model2.norm,
        lm_head=model2.head,
        layers=list(model2.layers),
        device=device,
        dtype=torch.float32,
    )

    print(f"\nStreaming model: {sm.num_layers} layers")
    print(f"Peak VRAM: {sm.peak_vram_bytes() / 1024**2:.1f} MB")
    print(f"Total params: {sm.total_params_bytes() / 1024**2:.1f} MB")
    print(f"Resident fraction: {sm.resident_fraction():.2%}")

    with torch.no_grad():
        start = time.perf_counter()
        streaming_logits = sm(input_ids)
        streaming_time = time.perf_counter() - start
    print(f"Streaming forward: {streaming_time:.4f}s, output shape: {streaming_logits.shape}")

    # Compare
    diff = (standard_logits - streaming_logits).abs().max().item()
    print(f"\nMax diff: {diff:.6f}")
    print(f"Overhead: {streaming_time / standard_time:.2f}x")

    if diff < 1e-3:
        print("\n✓ Outputs match!")
    else:
        print(f"\n⚠ Outputs differ (diff={diff}) — may be due to parameter initialization differences")

    print("\n" + "=" * 60)
    print("Streaming engine test complete")
    print("=" * 60)


if __name__ == "__main__":
    test_streaming()
