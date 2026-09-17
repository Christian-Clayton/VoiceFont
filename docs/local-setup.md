# Run VoiceFont locally on Windows

**How-to guide:** provision this checkout once, then launch it without network downloads.
For a Windows user new to VoiceFont; use a terminal only for setup. No GPU, Docker,
cloud account, API key or global Python package installation is required.

## Start the installed application

Double-click **Start VoiceFont.cmd** in the repository root. Keep its console open.
It starts the existing app using `uv run --offline --no-sync python -m voicefont serve`
on `127.0.0.1:8000`, waits up to 45 seconds for `/health`, then opens your default
browser at `/calibrate`. Press **Ctrl+C** in the console to stop the server and its
jobs. Closing only the browser does not stop the server.

The launcher does not install, update, download models, enroll fixtures or record
your microphone. Allow microphone access in your browser only when you choose to
record your own calibration. Profiles stay in the app's normal private registry
(default `~/.voicefont/profiles`; `VOICEFONT_HOME` can override its parent).

If port 8000 is occupied, stop the other server or run:

```bat
"Start VoiceFont.cmd" --port 8765
```

The launcher refuses occupied ports rather than opening an unrelated application.
It works when started outside the repository and quotes paths containing spaces.

## Provision or rebuild the inference environment

Prerequisites: Windows x64, [uv](https://docs.astral.sh/uv/), Python 3.11 for the
core app, and Python 3.10 for the isolated speech worker. Python 3.10.11 and
3.11.16 were exercised here. Do not activate the inference environment as your
app environment. Do not copy a virtual environment from another directory.

From the repository root, provision the core application once (free public
package downloads; this is deliberately separate from launching):

```bat
uv sync --python 3.11 --frozen --extra ml --extra dev
```

The existing **data/openvoice-runtime** bundle contains the pinned OpenVoice and
MeloTTS source, model weights, tokenizers, language resources, notices and manifest.
With that bundle present, run:

```bat
.venv\Scripts\python.exe scripts\setup_openvoice.py --python 3.10
```

Setup creates **.venv-openvoice** in this checkout, installs the 111 exact packages
in `requirements-openvoice.txt`, and checks installed dependency compatibility.
CPU torch/torchaudio wheels are explicitly from the official PyTorch download
host; other packages use the normal public Python index. No pip packages are
installed globally. Old inference-only pins are intentionally isolated from the
core application; this is not the full upstream training/ASR/UI installation.

Setup verifies all 194 public runtime files, runs actual neural generation with
network calls blocked by the existing worker, checks the official technical
fixture output against the seeded baseline, and **only then** atomically sets
`data/openvoice-runtime/config.json` to this checkout's inference interpreter.
Failure does not publish a new config. Do not run setup while the app is serving.
The first inference may need roughly two minutes for imports/cache preparation;
later verification on this machine took about 41 seconds. The worker timeout is
180 seconds.

After the uv cache has been populated, repeat without any package downloads:

```bat
.venv\Scripts\python.exe scripts\setup_openvoice.py --offline
```

To test and refresh paths without changing installed packages:

```bat
.venv\Scripts\python.exe scripts\setup_openvoice.py --verify-only
```

An explicit interpreter path is accepted by `--python` if version discovery fails.
If moving the checkout, recreate both virtual environments at their destination,
then rerun setup to refresh absolute runtime paths. Do not copy or move a venv.

## Runtime bundle prerequisite on a fresh checkout

The package setup script does **not** download the approximately 831 MB public
runtime bundle. Preserve/back up `data/openvoice-runtime` with its manifest and
notices. It is local, ignored data, not included in a source checkout or wheel.
The original promotion tool can create it from an already verified spike:

```bat
.venv\Scripts\python.exe scripts\provision_openvoice.py --source "C:\path\to\verified-spike" --reuse-python "C:\path\to\python310.exe"
.venv\Scripts\python.exe scripts\setup_openvoice.py --python 3.10
```

Promotion never copies a venv or personal voice data. A fresh machine without a
verified bundle still needs the explicit public-asset preparation described in
[the spike report](openvoice-spike.md) and the retained
`data/openvoice-runtime/provenance/README.md`. A turnkey fresh-machine asset
fetcher is not supplied by this setup script. Serving will never attempt it.
The [runtime report](openvoice-runtime.md) describes the serving boundaries.
**The current config no longer depends on the spike or anything under Temp**.

## Verify the installation

```bat
.venv\Scripts\python.exe scripts\launch_voicefont.py --no-browser --check --port 8765
uv run --offline --no-sync pytest scripts/setup_openvoice_test.py -q
set VOICEFONT_RUN_OPENVOICE_TEST=1
uv run --offline --no-sync pytest tests/test_synthesis.py::test_real_offline_technical_fixture -q
```

`--check` starts a real server, verifies health, and shuts it down; it does not
leave a daemon running. `--no-browser` is for automated/local headless checks.
The normal double-click path opens the browser only after readiness.

Verified on this machine:

- `.venv-openvoice`: recreated from pinned public packages, Python 3.10.11;
  `uv pip check` reported all 111 packages compatible.
- Offline setup and real synthesis-service/HTTP WAV-download test passed.
- Output: mono 22050 Hz, 3.413333 seconds, SHA256
  `31deaac0f90a71476002df1ddd99b147aff94dd3548dd2ec04a82b9894c3ae02`.
- Evidence: `data/openvoice-runtime/verification/durable-result.json` and
  `durable-technical-fixture.wav`; the config names `.venv-openvoice` explicitly.
- Launcher health reported `synthesis_available: true`; `/calibrate` returned
  HTTP 200. Startup and graceful shutdown were exercised.

The reference is upstream's official **technical fixture**, not your voice.
It is never enrolled as a user profile. Independent speaker release, listening
quality and speaker resemblance have not been established. The reduced pipeline
produces synthetic, unwatermarked output. Offline guards block Python socket
connections and HF downloads; this is not an OS-wide network sandbox.

Both `.venv-openvoice` and `data/` are ignored by Git. Keep private recordings out
of source control. No commits or cloud runtime operations are part of setup.
