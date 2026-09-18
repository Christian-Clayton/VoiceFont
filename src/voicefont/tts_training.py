"""Real CUDA TTS-style training: text-to-mel neural network with MLflow.

This trains a neural network to predict mel-spectrogram features from text
embeddings - the "acoustic model" component of a TTS system. It runs on real
CUDA tensors, tracks loss curves in MLflow, and saves checkpoints.

This is a demonstration model. Production TTS quality requires a full VITS/
Tacotron2 + HiFi-GAN pipeline trained on thousands of hours of speech.
"""
from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

REPO_ROOT = Path(__file__).resolve().parents[2]
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TtsTrainingConfig:
    run_name: str = "tts_text2mel_smoke"
    dataset_dir: str = str(REPO_ROOT / "training" / "piper_dataset")
    output_dir: str = str(REPO_ROOT / "training" / "tts_output")
    sample_rate: int = 22050
    batch_size: int = 8
    num_epochs: int = 10
    learning_rate: float = 0.001
    seed: int = 42
    hidden_dim: int = 256
    text_embed_dim: int = 64
    num_mels: int = 80

    def validate(self):
        if not 1 <= self.batch_size <= 64:
            raise ValueError("batch_size 1-64")
        return self


@dataclass
class TtsTrainingResult:
    run_id: str
    status: str
    final_loss: float
    best_loss: float
    epochs_trained: int
    training_duration_s: float
    peak_vram_mb: float
    checkpoints: list

    def to_dict(self):
        return asdict(self)


class TextToMelModel(nn.Module):
    """Simple text-to-mel acoustic model for TTS demonstration.

    Architecture: text embedding -> transformer-ish encoder -> mel prediction.
    Real systems use Tacotron2/FastSpeech2 + HiFi-GAN, but this demonstrates
    the core computation: learned text-to-acoustic-feature mapping on CUDA.
    """

    def __init__(self, vocab_size: int, embed_dim: int, hidden_dim: int,
                 num_mels: int, pad_idx: int = 0):
        super().__init__()
        self.text_embedding = nn.Embedding(vocab_size, embed_dim, padding_idx=pad_idx)
        self.encoder = nn.LSTM(embed_dim, hidden_dim, batch_first=True,
                               num_layers=2, dropout=0.1, bidirectional=True)
        self.mel_predictor = nn.Sequential(
            nn.Linear(hidden_dim * 2, hidden_dim),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(hidden_dim, num_mels),
        )
        self.num_mels = num_mels

    def forward(self, text_indices: torch.Tensor, text_lengths: torch.Tensor):
        """Predict mel features from text indices.

        Args:
            text_indices: (batch, max_text_len) character indices
            text_lengths: (batch,) actual lengths for packing

        Returns:
            mel_pred: (batch, max_text_len, num_mels) predicted mel features
        """
        embedded = self.text_embedding(text_indices)  # (B, T, E)

        # Pack for LSTM
        packed = nn.utils.rnn.pack_padded_sequence(
            embedded, text_lengths.cpu(), batch_first=True, enforce_sorted=False
        )
        encoded, _ = self.encoder(packed)
        encoded, _ = nn.utils.rnn.pad_packed_sequence(encoded, batch_first=True)

        mel_pred = self.mel_predictor(encoded)  # (B, T, num_mels)
        return mel_pred


def load_dataset_ljspeech(dataset_dir: str):
    """Load LJSpeech-format dataset."""
    import csv
    ds = Path(dataset_dir)
    meta = ds / "metadata.csv"
    wavs = ds / "wavs"
    records = []
    with open(meta, encoding="utf-8") as f:
        reader = csv.reader(f, delimiter="|")
        for row in reader:
            if len(row) < 2:
                continue
            fid, text = row[0], row[-1]
            wp = wavs / f"{fid}.wav"
            if wp.is_file():
                records.append((str(wp.resolve()), text))
    return records


def load_audio_mono(wav_path: str, target_sr: int = 22050) -> np.ndarray:
    """Load audio as mono float32."""
    import wave
    with wave.open(wav_path, "rb") as wf:
        assert wf.getnchannels() == 1
        assert wf.getsampwidth() == 2
        sr = wf.getframerate()
        frames = wf.getnframes()
        pcm = wf.readframes(frames)
    audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    if sr != target_sr:
        # Simple resampling
        import librosa
        audio = librosa.resample(audio, orig_sr=sr, target_sr=target_sr)
    return audio


def compute_mel_spectrogram(audio: np.ndarray, sr: int = 22050,
                            n_mels: int = 80, n_fft: int = 1024,
                            hop_length: int = 256) -> np.ndarray:
    """Compute mel spectrogram in dB."""
    import librosa
    mel = librosa.feature.melspectrogram(
        y=audio, sr=sr, n_mels=n_mels, n_fft=n_fft, hop_length=hop_length
    )
    mel_db = librosa.power_to_db(mel, ref=np.max)
    return mel_db.T  # (time, n_mels)


def text_to_indices(text: str, char_to_idx: dict, max_len: int = 200) -> list:
    """Convert text to character indices."""
    indices = [char_to_idx.get(c, char_to_idx[" "]) for c in text[:max_len]]
    return indices


def get_char_vocab() -> dict:
    """Simple character vocabulary."""
    chars = "abcdefghijklmnopqrstuvwxyz!'(),-.:;? "
    return {c: i + 1 for i, c in enumerate(chars)}  # 0 = padding


def train_text2mel(config: TtsTrainingConfig) -> TtsTrainingResult:
    """Train the text-to-mel model on CUDA with MLflow tracking."""
    config = config.validate()

    # CUDA check
    assert torch.cuda.is_available(), "CUDA required"
    device = torch.device("cuda:0")
    print(f"GPU: {torch.cuda.get_device_name(0)}")
    print(f"VRAM: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")

    # Load dataset
    records = load_dataset_ljspeech(config.dataset_dir)
    assert len(records) >= 2, f"need >= 2 samples, got {len(records)}"
    print(f"Loaded {len(records)} samples")

    # Build vocabulary
    char_to_idx = get_char_vocab()
    vocab_size = len(char_to_idx) + 1  # +1 for padding

    # Precompute mel targets and text indices
    print("Precomputing mel spectrograms...")
    texts = []
    mel_targets = []
    for wav_path, text in records:
        audio = load_audio_mono(wav_path, config.sample_rate)
        mel = compute_mel_spectrogram(audio, config.sample_rate, config.num_mels)
        mel_targets.append(torch.from_numpy(mel).float())
        texts.append(text_to_indices(text, char_to_idx))

    print(f"Computed {len(mel_targets)} mel targets")
    print(f"Mel shape example: {mel_targets[0].shape}")

    # Build model
    model = TextToMelModel(
        vocab_size=vocab_size,
        embed_dim=config.text_embed_dim,
        hidden_dim=config.hidden_dim,
        num_mels=config.num_mels,
    ).to(device)
    print(f"Model: {type(model).__name__}")
    print(f"Params: {sum(p.numel() for p in model.parameters()):,}")

    # Optimizer
    optimizer = torch.optim.Adam(model.parameters(), lr=config.learning_rate)
    scheduler = torch.optim.lr_scheduler.StepLR(optimizer, step_size=5, gamma=0.5)

    # MLflow
    import mlflow
    out = Path(config.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    mlflow.set_tracking_uri(f"file:{out / 'mlflow'}")
    mlflow.set_experiment("voicefont-tts-text2mel")

    run = mlflow.start_run(run_name=config.run_name)
    run_id = run.info.run_id
    mlflow.log_params(asdict(config))

    best_loss = float("inf")
    final_loss = float("inf")
    peak_vram = 0.0
    checkpoints = []
    started = time.time()

    for epoch in range(config.num_epochs):
        model.train()
        epoch_losses = []
        idx = list(range(len(records)))
        np.random.shuffle(idx)

        for start in range(0, len(idx), config.batch_size):
            batch_idx = idx[start:start + config.batch_size]
            batch_texts = [torch.tensor(texts[i], dtype=torch.long) for i in batch_idx]
            batch_mels = [mel_targets[i] for i in batch_idx]

            # Pad
            text_lens = torch.tensor([t.size(0) for t in batch_texts], dtype=torch.long)
            max_text = max(t.size(0) for t in batch_texts)
            texts_padded = torch.zeros(len(batch_texts), max_text, dtype=torch.long, device=device)
            for i, t in enumerate(batch_texts):
                texts_padded[i, :t.size(0)] = t

            mel_lens = [m.size(0) for m in batch_mels]
            max_mel = max(mel_lens)
            mels_padded = torch.zeros(len(batch_mels), max_mel, config.num_mels, device=device)
            mel_mask = torch.zeros(len(batch_mels), max_mel, dtype=torch.bool, device=device)
            for i, m in enumerate(batch_mels):
                mels_padded[i, :m.size(0), :] = m.to(device)
                mel_mask[i, :m.size(0)] = True

            # Forward
            optimizer.zero_grad()
            mel_pred = model(texts_padded, text_lens)

            # Only compute loss on valid (non-padded) positions
            # Align: text positions -> mel positions via repeating
            # Simple approach: min length
            min_len = min(mel_pred.size(1), mels_padded.size(1))
            pred = mel_pred[:, :min_len, :]
            target = mels_padded[:, :min_len, :]
            mask = mel_mask[:, :min_len].unsqueeze(-1).float()

            loss = ((pred - target) ** 2 * mask).sum() / mask.sum()

            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()

            bl = loss.item()
            epoch_losses.append(bl)

            vram = torch.cuda.max_memory_allocated() / 1024**2
            if vram > peak_vram:
                peak_vram = vram

        scheduler.step()
        final_loss = float(np.mean(epoch_losses)) if epoch_losses else 0.0
        mlflow.log_metric("epoch_loss", final_loss, step=epoch)
        mlflow.log_metric("peak_vram_mb", peak_vram, step=epoch)
        mlflow.log_metric("lr", optimizer.param_groups[0]["lr"], step=epoch)

        if final_loss < best_loss:
            best_loss = final_loss
            ckpt_path = out / f"ckpt_epoch_{epoch}.pth"
            torch.save({
                "epoch": epoch,
                "model_state_dict": model.state_dict(),
                "optimizer_state_dict": optimizer.state_dict(),
                "loss": best_loss,
                "config": asdict(config),
            }, ckpt_path)
            mlflow.log_artifact(str(ckpt_path), "checkpoints")
            checkpoints.append(str(ckpt_path))

        print(f"Epoch {epoch}: loss={final_loss:.4f} best={best_loss:.4f} vram={peak_vram:.0f}MB")

    duration = time.time() - started
    mlflow.log_metrics({
        "final_loss": final_loss, "best_loss": best_loss,
        "duration_s": duration, "peak_vram_mb": peak_vram,
    })
    mlflow.end_run()

    return TtsTrainingResult(
        run_id=run_id, status="completed",
        final_loss=final_loss, best_loss=best_loss,
        epochs_trained=config.num_epochs,
        training_duration_s=duration, peak_vram_mb=peak_vram,
        checkpoints=checkpoints,
    )


if __name__ == "__main__":
    config = TtsTrainingConfig()
    result = train_text2mel(config)
    print(f"\nResult: {result}")
