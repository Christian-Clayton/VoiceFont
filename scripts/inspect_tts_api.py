"""Inspect TTS model to understand training API."""
import sys

sys.path.insert(0, 'src')

import TTS

print(f'TTS version: {TTS.__version__}')

from TTS.tts.configs.vits_config import VitsConfig
from TTS.tts.models.vits import Vits
from TTS.utils.audio import AudioProcessor

# Build config
vcfg = VitsConfig(
    audio={
        'fft_size': 1024, 'win_length': 1024, 'hop_length': 256,
        'sample_rate': 22050, 'num_mels': 80, 'mel_fmin': 0, 'mel_fmax': 8000,
    },
    batch_size=4,
    epochs=1,
    run_eval=False,
    use_speaker_embedding=False,
    num_speakers=1,
    output_path='training/tts_output',
    datasets=[{
        'name': 'vf_ds', 'path': 'training/piper_dataset',
        'meta_file_train': 'metadata.csv', 'meta_file_val': None,
        'ignored_speakers': [],
    }],
)

ap = AudioProcessor.init_from_config(vcfg)
model = Vits(vcfg, ap, None, None, None)
model = model.cuda()

print(f'Model params: {sum(p.numel() for p in model.parameters()):,}')
print(f'Has training_step: {hasattr(model, "training_step")}')
print(f'Has optimize: {hasattr(model, "optimize")}')
print(f'Has forward: {hasattr(model, "forward")}')

# Try to understand the training API
import inspect

print(f'\noptimize signature: {inspect.signature(model.optimize)}')
print(f'forward signature: {inspect.signature(model.forward)}')

# Check Coqui TTS bin for training scripts
import os

tts_path = os.path.dirname(TTS.__file__)
print(f'\nTTS path: {tts_path}')
print(f'Bin contents: {os.listdir(os.path.join(tts_path, "bin"))}')
