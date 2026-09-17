"""Use Coqui's train_tts.py directly with a config file."""
import os
import json
import tempfile
import subprocess
import sys

# Create VITS training config
config = {
    "model": "vits",
    "run_name": "voicefont_vits_smoke",
    "project_name": "voicefont-tts",
    "output_path": "training/tts_output",
    "batch_size": 4,
    "eval_batch_size": 4,
    "num_loader_workers": 0,
    "num_eval_loader_workers": 0,
    "epochs": 3,
    "text_cleaner": "english_cleaners",
    "use_phonemes": False,
    "phoneme_language": "en-us",
    "run_eval": True,
    "eval_split_size": 0.1,
    "lr_gen": 0.001,
    "lr_disc": 0.0005,
    "mixed_precision": False,
    "use_speaker_embedding": False,
    "num_speakers": 1,
    "audio": {
        "fft_size": 1024,
        "win_length": 1024,
        "hop_length": 256,
        "sample_rate": 22050,
        "num_mels": 80,
        "mel_fmin": 0,
        "mel_fmax": 8000
    },
    "datasets": [
        {
            "name": "vf_ds",
            "path": "training/piper_dataset",
            "meta_file_train": "metadata.csv",
            "meta_file_val": None,
            "ignored_speakers": [],
            "formatter": "ljspeech",
            "dataset_name": "voicefont_dataset",
            "language": "en-us"
        }
    ]
}

config_path = "training/vits_config.json"
with open(config_path, "w") as f:
    json.dump(config, f, indent=2)

print(f"Config written to {config_path}")
print(json.dumps(config, indent=2))
