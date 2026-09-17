"""Explicit online provisioning only. Runtime never calls this module."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
MODEL_REV = '1464ca7a7269f8c2c07c94a63455216a38836dca'
MODEL_HASH = '0575cb64845e6b9a10db9bcb74d5ac32b326b8dc90352671d345e2ee3d0126a2'
FIXTURES = {
    'kathleen': ('c51cb971036a127359b43c621f26ca5081eab13e', [
        'data/arctic_a0001_1592748574.wav', 'data/arctic_a0002_1592748530.wav',
        'data/arctic_a0003_1592748500.wav']),
    'flemishguy': ('2576e9c8e5b6eec92e45010b5ede87c4f836f21e', [
        'wavs/nl_rhasspy_1000_1601817815.wav', 'wavs/nl_rhasspy_1001_1601817805.wav',
        'wavs/nl_rhasspy_1002_1601817789.wav']),
}


def download(url, target, expected=None):
    target.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=90) as response:
        raw = response.read(100 * 1024 * 1024 + 1)
    if len(raw) > 100 * 1024 * 1024:
        raise ValueError('asset too large')
    digest = hashlib.sha256(raw).hexdigest()
    if expected is not None and digest != expected:
        raise ValueError('asset hash mismatch')
    target.write_bytes(raw)
    return {'url': url, 'path': str(target.relative_to(ROOT)), 'sha256': digest, 'bytes': len(raw)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--authorize-public-fixtures', action='store_true', required=True)
    parser.parse_args()
    output = ROOT / 'data/embeddings'
    model_base = f'https://huggingface.co/speechbrain/spkrec-ecapa-voxceleb/resolve/{MODEL_REV}'
    manifest = {'model_revision': MODEL_REV, 'model_license': 'Apache-2.0', 'artifacts': [],
                'fixtures': [], 'fixture_use': 'CC0 published voice datasets; technical retrieval only, not user enrollments'}
    manifest['artifacts'].append(download(model_base + '/embedding_model.ckpt', output / 'embedding_model.ckpt', MODEL_HASH))
    manifest['artifacts'].append(download(model_base + '/README.md', output / 'MODEL-README.md'))
    manifest['artifacts'].append(download('https://www.apache.org/licenses/LICENSE-2.0.txt', output / 'MODEL-LICENSE.txt'))
    for speaker, (revision, files) in FIXTURES.items():
        base = f'https://raw.githubusercontent.com/rhasspy/dataset-voice-{speaker}/{revision}'
        for notice in ('LICENSE', 'README.md'):
            manifest['artifacts'].append(download(base + '/' + notice, output / 'fixtures' / speaker / notice))
        for i, filename in enumerate(files):
            record = download(base + '/' + filename, output / 'fixtures' / speaker / f'{i}.wav')
            record.update(speaker=speaker, source_revision=revision, license='CC0-1.0',
                          consent=True, split='gallery' if i == 0 else 'query')
            manifest['fixtures'].append(record)
    (output / 'provenance.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(json.dumps({'provenance': str(output / 'provenance.json'), 'fixture_count': len(manifest['fixtures'])}))


if __name__ == '__main__':
    main()
