"""Tests for tts_training.py: CUDA text-to-mel training with MLflow."""
from dataclasses import asdict
from unittest.mock import MagicMock, patch

import pytest

from voicefont.tts_training import (
    TextToMelModel,
    TtsTrainingConfig,
    TtsTrainingResult,
    get_char_vocab,
    load_dataset_ljspeech,
    text_to_indices,
    train_text2mel,
)


class TestTtsTrainingConfig:
    def test_default_config(self):
        config = TtsTrainingConfig()
        assert config.batch_size == 8
        assert config.num_epochs == 10
        assert config.learning_rate == 0.001
        assert config.hidden_dim == 256

    def test_validate_valid_config(self):
        config = TtsTrainingConfig(batch_size=16, num_epochs=5)
        validated = config.validate()
        assert validated.batch_size == 16

    def test_validate_invalid_batch_size_low(self):
        config = TtsTrainingConfig(batch_size=0)
        with pytest.raises(ValueError, match="batch_size 1-64"):
            config.validate()

    def test_validate_invalid_batch_size_high(self):
        config = TtsTrainingConfig(batch_size=65)
        with pytest.raises(ValueError, match="batch_size 1-64"):
            config.validate()

    def test_config_frozen(self):
        config = TtsTrainingConfig()
        with pytest.raises(AttributeError):
            config.batch_size = 16

    def test_config_to_dict(self):
        config = TtsTrainingConfig()
        d = asdict(config)
        assert "batch_size" in d
        assert "learning_rate" in d


class TestTtsTrainingResult:
    def test_to_dict(self):
        result = TtsTrainingResult(
            run_id="r1",
            status="completed",
            final_loss=0.1,
            best_loss=0.05,
            epochs_trained=10,
            training_duration_s=5.0,
            peak_vram_mb=1024.0,
            checkpoints=["/tmp/ckpt.pth"],
        )
        d = result.to_dict()
        assert d["run_id"] == "r1"
        assert d["final_loss"] == 0.1
        assert d["checkpoints"] == ["/tmp/ckpt.pth"]

    def test_to_dict_empty_checkpoints(self):
        result = TtsTrainingResult(
            run_id="r2",
            status="completed",
            final_loss=1.0,
            best_loss=1.0,
            epochs_trained=0,
            training_duration_s=0.0,
            peak_vram_mb=0.0,
            checkpoints=[],
        )
        d = result.to_dict()
        assert d["checkpoints"] == []


class TestTextToMelModel:
    def test_model_creation(self):
        model = TextToMelModel(vocab_size=40, embed_dim=64, hidden_dim=256, num_mels=80)
        assert model.num_mels == 80
        params = sum(p.numel() for p in model.parameters())
        assert params > 0

    def test_model_forward(self):
        model = TextToMelModel(vocab_size=40, embed_dim=64, hidden_dim=32, num_mels=8)
        import torch
        batch_size = 2
        seq_len = 10
        text_indices = torch.randint(0, 40, (batch_size, seq_len))
        text_lengths = torch.tensor([seq_len, seq_len])
        model.eval()
        with torch.no_grad():
            output = model(text_indices, text_lengths)
        assert output.shape == (batch_size, seq_len, 8)

    def test_model_forward_variable_lengths(self):
        model = TextToMelModel(vocab_size=40, embed_dim=32, hidden_dim=16, num_mels=4)
        import torch
        text_indices = torch.randint(0, 40, (3, 15))
        text_lengths = torch.tensor([15, 10, 5])
        model.eval()
        with torch.no_grad():
            output = model(text_indices, text_lengths)
        assert output.shape == (3, 15, 4)


class TestHelperFunctions:
    def test_get_char_vocab(self):
        vocab = get_char_vocab()
        assert "a" in vocab
        assert "z" in vocab
        assert " " in vocab
        # 0 is reserved for padding
        assert all(v >= 1 for v in vocab.values())

    def test_text_to_indices(self):
        vocab = get_char_vocab()
        indices = text_to_indices("hello", vocab)
        assert len(indices) == 5
        assert all(isinstance(i, int) for i in indices)

    def test_text_to_indices_max_len(self):
        vocab = get_char_vocab()
        long_text = "a" * 300
        indices = text_to_indices(long_text, vocab, max_len=50)
        assert len(indices) == 50

    def test_text_to_indices_unknown_char(self):
        vocab = get_char_vocab()
        # "@" is not in vocab, should map to space index
        indices = text_to_indices("@", vocab)
        assert indices[0] == vocab[" "]

    def test_load_dataset_ljspeech_missing_dir(self, tmp_path):
        """Missing metadata.csv raises FileNotFoundError."""
        empty_dir = tmp_path / "empty_ds"
        empty_dir.mkdir()
        with pytest.raises(FileNotFoundError):
            load_dataset_ljspeech(str(empty_dir))

    def test_load_dataset_ljspeech_with_data(self, tmp_path):
        """Loads records from a valid LJSpeech-format directory."""
        ds_dir = tmp_path / "ljspeech"
        ds_dir.mkdir()
        wavs_dir = ds_dir / "wavs"
        wavs_dir.mkdir()

        # Create metadata.csv
        metadata = ds_dir / "metadata.csv"
        metadata.write_text("id1|Hello world|Hello world\nid2|Test text|Test text\n")

        # Create dummy wav files (just empty files for existence check)
        (wavs_dir / "id1.wav").write_bytes(b"")
        (wavs_dir / "id2.wav").write_bytes(b"")

        result = load_dataset_ljspeech(str(ds_dir))
        assert len(result) == 2
        assert result[0][1] == "Hello world"
        assert result[1][1] == "Test text"

    def test_load_dataset_ljspeech_missing_wav(self, tmp_path):
        """Records without corresponding wav files are skipped."""
        ds_dir = tmp_path / "ljspeech"
        ds_dir.mkdir()
        wavs_dir = ds_dir / "wavs"
        wavs_dir.mkdir()

        metadata = ds_dir / "metadata.csv"
        metadata.write_text("id1|Hello world|Hello world\nid2|Test text|Test text\n")

        # Only create id1.wav, skip id2.wav
        (wavs_dir / "id1.wav").write_bytes(b"")

        result = load_dataset_ljspeech(str(ds_dir))
        assert len(result) == 1

    def test_load_dataset_ljspeech_short_rows_skipped(self, tmp_path):
        """Rows with fewer than 2 columns are skipped."""
        ds_dir = tmp_path / "ljspeech"
        ds_dir.mkdir()
        wavs_dir = ds_dir / "wavs"
        wavs_dir.mkdir()

        metadata = ds_dir / "metadata.csv"
        metadata.write_text("short_row\nid1|Hello world|Hello world\n")
        (wavs_dir / "id1.wav").write_bytes(b"")

        result = load_dataset_ljspeech(str(ds_dir))
        assert len(result) == 1



class TestTrainText2melMocked:
    """Test train_text2mel setup logic with mocked CUDA/dataset."""

    def test_training_config_validated_before_use(self):
        """TtsTrainingConfig.validate is called at start."""
        from voicefont.tts_training import train_text2mel

        config = TtsTrainingConfig(batch_size=999)
        with patch("torch.cuda.is_available", return_value=True):
            with pytest.raises(ValueError, match="batch_size"):
                train_text2mel(config)

    def test_training_min_samples_check(self, tmp_path):
        """Asserts >= 2 samples required."""
        mock_run = MagicMock()
        mock_run.info.run_id = "mlflow-run-123"
        mock_mlflow = MagicMock()
        mock_mlflow.start_run.return_value = mock_run

        with patch.dict("sys.modules", {"mlflow": mock_mlflow}), \
             patch("voicefont.tts_training.compute_mel_spectrogram"), \
             patch("voicefont.tts_training.load_audio_mono"), \
             patch("voicefont.tts_training.load_dataset_ljspeech") as mock_load_ds, \
             patch("torch.cuda.is_available", return_value=True), \
             patch("torch.cuda.get_device_name", return_value="Mock GPU"), \
             patch("torch.cuda.get_device_properties") as mock_props:

            # Only 1 sample - should fail
            mock_load_ds.return_value = [("/tmp/wav1.wav", "Hello")]
            mock_props.return_value = MagicMock(total_memory=8 * 1024**3)

            config = TtsTrainingConfig(
                dataset_dir=str(tmp_path / "ds"),
                output_dir=str(tmp_path / "out"),
            )

            with pytest.raises(AssertionError, match="need >= 2 samples"):
                train_text2mel(config)

    @patch.dict("sys.modules", {"mlflow": MagicMock()})
    def test_training_requires_cuda(self):
        """Asserts CUDA is required."""
        from voicefont.tts_training import train_text2mel

        config = TtsTrainingConfig()
        with patch("torch.cuda.is_available", return_value=False):
            with pytest.raises(AssertionError, match="CUDA required"):
                train_text2mel(config)

    @patch("voicefont.tts_training.compute_mel_spectrogram")
    @patch("voicefont.tts_training.load_audio_mono")
    @patch("voicefont.tts_training.load_dataset_ljspeech")
    @patch.dict("sys.modules", {"mlflow": MagicMock()})
    def test_training_dataset_preprocessing(self, mock_load_ds, mock_load_audio, mock_mel):
        """Dataset is loaded and mel spectrograms are precomputed."""
        import numpy as np

        mock_load_ds.return_value = [
            ("/tmp/wav1.wav", "Hello world"),
            ("/tmp/wav2.wav", "Test text"),
        ]
        mock_load_audio.return_value = np.random.randn(22050).astype(np.float32)
        mock_mel.return_value = np.random.randn(50, 8).astype(np.float32)

        # Stop after dataset loading
        with patch("voicefont.tts_training.TextToMelModel") as mock_model_cls, \
             patch("torch.cuda.is_available", return_value=True), \
             patch("torch.cuda.get_device_name", return_value="Mock GPU"), \
             patch("torch.cuda.get_device_properties") as mock_props, \
             patch("torch.optim.Adam"):

            mock_props.return_value = MagicMock(total_memory=8 * 1024**3)
            # Make model creation fail after dataset loading
            mock_model_cls.side_effect = RuntimeError("Stop after dataset loading")

            config = TtsTrainingConfig(
                dataset_dir="/fake/ds",
                output_dir="/fake/out",
                num_epochs=2,
                batch_size=2,
            )

            with pytest.raises(RuntimeError, match="Stop after dataset loading"):
                train_text2mel(config)

            # Verify the dataset was loaded
            mock_load_ds.assert_called_once_with("/fake/ds")
            assert mock_load_audio.call_count == 2
            assert mock_mel.call_count == 2
