# OpenVoice V2: local feasibility verified

This is a technical feasibility report, not an installed VoiceFont backend or a voice-quality assessment.

## Observed result

The parent reran genuine MeloTTS English v3 -> OpenVoice V2 on Windows CPU with Hugging Face offline flags and Python socket connections blocked. The complete pipeline produced a non-silent, decodable WAV from this text:

> This is a local speech test. No cloud service is used.

- Runtime environment: Python 3.10.11, torch 2.2.2+cpu.
- Parent pipeline time: 26.71 seconds including model loading and reference extraction, excluding imports.
- Output: 3.4133 seconds, mono, 22050 Hz.
- Output SHA256: `31deaac0f90a71476002df1ddd99b147aff94dd3548dd2ec04a82b9894c3ae02`.
- Converter checkpoint: no missing or unexpected keys.
- Verification passed: reference hash, V2 version, offline completion, seeded online/offline output equality, finite non-silent PCM and ffmpeg decoding.

This is reference-based zero-shot tone conversion, not personal model fine-tuning. No listening, ASR intelligibility, speaker resemblance, GPU or concurrency assessment has been performed. It is not real-time on this CPU run.

## Local evidence location

The isolated spike environment and artifacts are at:

`C:/Users/Chris/AppData/Local/Temp/voicefont-openvoice-spike`

Important files: `README.md`, `smoke.py`, `verify_artifacts.py`, `requirements-frozen.txt`, `download-manifest.json`, `cached-resource-manifest.json`, `openvoice-spike.patch`, `outputs/result-offline.json`, `outputs/openvoice-v2.wav`.

The temporary environment is not a portable installation or a long-term deployment. The active VoiceFont environment is Python 3.11 and must not inherit these older dependencies indiscriminately.

Repeat the verified test from the spike directory:

```bash
.venv/Scripts/python.exe smoke.py --offline
.venv/Scripts/python.exe verify_artifacts.py
```

## Compatibility findings

The official installation path failed during PyAV/Cython dependency preparation. A bounded inference-only installation succeeded by omitting optional ASR/VAD, UI and watermark dependencies, using direct reference embedding extraction on the supplied clean fixture.

Required compatibility changes were:

1. Pin setuptools 80.9.0 because the old librosa needs `pkg_resources`.
2. Provision the modern NLTK `averaged_perceptron_tagger_eng` resource.
3. Apply a spike-only constructor signature patch to permit OpenVoice's existing `enable_watermark=False` option. No neural layers or inference mathematics were replaced.

The output is explicitly synthetic test audio and is not watermarked. This reduced environment is not the full supported upstream installation. Keep the patch explicit and isolate inference behind a process boundary when integrating it.

## Provenance and licensing boundaries

- OpenVoice revision: `74a1d147b17a8c3092dd5430504bd83ef6c7eb23`.
- MeloTTS revision: `209145371cff8fc3bd60d7be902ea69cbdb7965a`.
- Official reference: `OpenVoice/resources/example_reference.mp3`, SHA256 `d0f5806f6e034e660c46a0b2fe4c597f0a1670859743c14e27a8823a7d169263`.
- The reference is an official example in the MIT repository, not the user's voice. No independent speaker release was verified. Restrict it to this technical fixture demonstration, not user enrollment or identity impersonation.
- OpenVoice and Melo declare MIT; BERT declares Apache-2.0. Preserve notices. Transitive dependencies and redistribution rights need a separate review.
- Approximately 779 MB of model weights were downloaded during explicit setup. Runtime used no hosted inference or paid services. Offline guards cover Python socket calls, not an OS-wide firewall.

Upstream usage reference: https://github.com/myshell-ai/OpenVoice/blob/74a1d147b17a8c3092dd5430504bd83ef6c7eb23/docs/USAGE.md

## Next integration gate

Build a bounded subprocess adapter using this explicitly provisioned environment, caller-authorized profile references and controlled output paths. Reject missing assets rather than downloading at runtime. Add real end-to-end tests, dependency/security review and human listening evidence before enabling `/speak`. Until then the application correctly reports synthesis unavailable.
