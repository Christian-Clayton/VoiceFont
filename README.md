# VoiceFont

**How-to guide:** run the local React voice workspace and its tests. For developers new to this repository.

React 19 + Vite frontend, FastAPI backend, local PCM recording, 75-prompt calibration, immutable voice profiles, offline OpenVoice synthesis and opt-in acoustic ML experiments. No paid/cloud runtime, hosted tests, CDN assets or remote voice uploads.

## Start on this machine

Double-click **Start VoiceFont.cmd**. It opens `http://127.0.0.1:8000/calibrate` after the local server is ready. Keep the console open; Ctrl+C stops it.

The React production bundle and local speech runtime are already built on this machine. Node is needed to develop/build the UI, not to serve the built app.

## Development setup

Requires Python 3.11, uv, Node 22.12+ and npm. From the repository root:

```bash
uv sync --extra ml --extra dev
npm --prefix frontend ci --ignore-scripts
npm --prefix frontend run build
uv run --offline voicefont serve
```

Initial provisioning downloads free public packages. After dependencies are cached, `npm ci --offline --ignore-scripts` and `uv sync --frozen --offline --extra ml --extra dev` can install without network access. Runtime and verification remain local.

React components live in `frontend/src/`: `Calibration.jsx`, `Speech.jsx`, `Experiments.jsx` and `main.jsx`. Edit these, then rebuild with `npm --prefix frontend run build`. FastAPI serves `frontend/dist` from the checkout. The Python wheel includes the same compiled bundle under `voicefont/web`. An unbuilt frontend reports a clear 503, not an old HTML fallback.

Speech provisioning is separate: see [local setup](docs/local-setup.md). The durable Python 3.10 runtime is `.venv-openvoice`, not a temporary directory. **A fresh checkout still needs the prepared public model asset bundle**; a complete fresh-machine model downloader is not provided. Do not interpret this machine's successful setup as a fully automated distributable installer.

## Use the workspace

1. Confirm ownership or explicit permission and start a recording session.
2. Read each prompt naturally. Record, stop, replay and save, or import an authorised PCM WAV. Retakes preserve earlier accepted recordings.
3. Resume saved sessions, skip uncomfortable optional prompts and export a ZIP backup.
4. Create a partial profile after at least three accepted prompts from two categories. The server selects a neutral reference and preserves the whole session.
5. Use **Create speech** for local neutral-style synthesis, job status/cancellation and WAV download.
6. Optionally authorise **Acoustic ML** training after eight distinct selected original WAVs. See heldout reconstruction error versus baseline, the evaluation gate and local MLflow run ID.

The printable [Calibration Checklist](docs/Calibration%20Checklist.md) contains 75 prompts across seven categories, including 54 core prompts. Coverage counts recordings, not verified phonemes or every facet of a voice. Speak in your natural accent and never strain.

## Verify locally

```bash
npm --prefix frontend test
npm --prefix frontend run build
uv run --offline pytest tests scripts/setup_openvoice_test.py -q
uv run --offline ruff check src tests scripts
uv run --offline python scripts/browser_e2e.py
uv build --wheel
```

Browser testing needs the free Playwright Python package and installed Chrome/Edge. Provision once with `uv pip install --python .venv/Scripts/python.exe playwright==1.63.0`. Tests use generated microphone signals, isolated temporary data and a real local browser. No private microphone is used.

The heavyweight speech test is opt-in: set `VOICEFONT_RUN_OPENVOICE_TEST=1` and run `pytest tests/test_synthesis.py::test_real_offline_technical_fixture`. It uses an official technical fixture, never enrolls it as a user's voice, and blocks Python network connections during inference. This is not an OS firewall or a human voice-quality assessment.

## Boundaries and remaining work

- OpenVoice reference-based conversion is not fine-tuning. Only neutral style and speed 0.75-1.5 are supported; captured expressive styles are not trained TTS controls.
- Acoustic reconstruction uses real scikit-learn, LangGraph and local MLflow, but is not speaker identification or voice cloning. Search still uses deterministic acoustic descriptors.
- No human listening, intelligibility or speaker-similarity acceptance has been completed. Your microphone and voice need your own listening assessment.
- Profiles and sessions default under `~/.voicefont`; `VOICEFONT_HOME` selects a different home. Keep it private. Consent revocation/deletion workflows remain unimplemented.
- Loopback-only, single-user, unauthenticated service. Do not expose it publicly. The standard launcher disables sensitive access logs.
- Optional Weaviate, Triton, Kubernetes/Helm, Terraform, streaming and multi-style synthesis remain roadmap items, not delivered features.

Original plans remain byte-exact in `docs/planning/archive/`. Private recordings, model weights, runtime environments and build output are excluded from Git. Nothing is automatically published or pushed.
