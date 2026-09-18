"""Verify Coqui TTS training setup before running full training."""
import sys

sys.path.insert(0, 'src')

import torch
import TTS

print(f'TTS version: {TTS.__version__}')
print(f'CUDA available: {torch.cuda.is_available()}')


from trainer import Trainer
from TTS.tts.configs.vits_config import VitsConfig
from TTS.tts.datasets import load_tts_samples
from TTS.tts.models import setup_model

# Build config
vcfg = VitsConfig(
    audio={
        'fft_size': 1024, 'win_length': 1024, 'hop_length': 256,
        'sample_rate': 22050, 'num_mels': 80, 'mel_fmin': 0, 'mel_fmax': 8000,
    },
    batch_size=4,
    epochs=1,
    run_eval=True,
    eval_split_size=0.1,
    text_cleaner='english_cleaners',
    use_phonemes=False,
    output_path='training/tts_output',
    datasets=[{
        'name': 'vf_ds', 'path': 'training/piper_dataset',
        'meta_file_train': 'metadata.csv', 'meta_file_val': None,
        'ignored_speakers': [],
    }],
    use_speaker_embedding=False, num_speakers=1,
)
vcfg.load_json = False

# Load samples
train_samples, eval_samples = load_tts_samples(
    vcfg.datasets, eval_split=True,
    eval_split_max_size=vcfg.eval_split_max_size,
    eval_split_size=vcfg.eval_split_size,
)
print(f'Train: {len(train_samples)}, Eval: {len(eval_samples)}')
if len(train_samples) < 2:
    print('ERROR: Need at least 2 samples!')
    sys.exit(1)

# Build model
model = setup_model(vcfg, train_samples + eval_samples)
model = model.cuda()
print(f'Model: {type(model).__name__}, params: {sum(p.numel() for p in model.parameters()):,}')

# Check Trainer API
import inspect

print(f'Trainer __init__ sig: {inspect.signature(Trainer.__init__)}')
print(f'Trainer has fit: {hasattr(Trainer, "fit")}')
if hasattr(Trainer, 'callbacks'):
    print('Trainer has callbacks attr')
print('Setup OK')
