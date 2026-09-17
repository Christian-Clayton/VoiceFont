"""One request on stdin, one JSON response on stdout, then release CUDA.

Launch with the isolated embedding Python. Never a daemon; caller must bound
concurrency to one shared GPU job and apply a 90-second subprocess timeout.
"""
from __future__ import annotations

import contextlib
import json
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))


def run(request):
    from voicefont.embeddings import CudaSpeakerEncoder, require_consent

    if not isinstance(request, dict) or request.get('operation') != 'encode':
        raise ValueError('operation must be encode')
    require_consent(request.get('consent'))
    if not isinstance(request.get('audio_path'), str):
        raise ValueError('audio_path must be a local PCM WAV path')
    model_dir = request.get('model_dir', str(ROOT / 'data/embeddings'))
    with CudaSpeakerEncoder(model_dir, consent=True) as encoder:
        return {'ok': True, 'embedding': encoder.encode(request['audio_path'], consent=True).to_dict()}


def main():
    # Fail closed on all Python socket connections, including library loaders.
    def offline(*_args, **_kwargs):
        raise RuntimeError('embedding worker network disabled')
    socket.socket.connect = offline
    socket.socket.connect_ex = offline
    socket.create_connection = offline
    try:
        raw = sys.stdin.buffer.readline(65537)
        if len(raw) > 65536:
            raise ValueError('request exceeds 64 KiB')
        request = json.loads(raw)
        # Third-party diagnostic prints must not corrupt the JSON protocol.
        with contextlib.redirect_stdout(sys.stderr):
            response = run(request)
        code = 0
    except Exception as exc:
        # No paths, audio, checkpoints, stack traces or library bodies in errors.
        response = {'ok': False, 'error': {'code': type(exc).__name__,
                                          'message': 'embedding request failed; check consent, WAV, pinned assets and CUDA'}}
        code = 1
    print(json.dumps(response, allow_nan=False), flush=True)
    return code


if __name__ == '__main__':
    raise SystemExit(main())
