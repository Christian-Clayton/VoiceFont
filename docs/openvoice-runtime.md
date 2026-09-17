# Offline OpenVoice runtime: bounded local speech synthesis

Status: implemented and tested. The service produces genuine neural speech
through the exact pipeline verified in the spike: MeloTTS English v3, then
OpenVoice V2 tone conversion, in a single bounded subprocess on CPU, with
network access blocked inside the worker. A real end-to-end run through the job
service produced the known fixture output (3.413 s, 22050 Hz, SHA-256
`31deaac0f90a71476002df1ddd99b147aff94dd3548dd2ec04a82b9894c3ae02`), matching
the spike's verified artifact byte for byte.

## What runs where

- Core API (Python 3.11) never imports torch or OpenVoice. It validates jobs,
  enforces consent, bounds the queue, cancels workers and serves audio.
- `scripts/openvoice_worker.py` runs in the isolated Python 3.10 environment.
  It reads one UTF-8 JSON request from stdin (text never appears in argv or
  logs), redirects stdout/stderr to the null device at the descriptor level
  before any import, sets offline flags and local cache paths, blocks Python
  sockets, verifies every runtime file hash from `runtime-manifest.json` before
  deserializing any checkpoint, pins tokenizer loads to the exact provisioned
  HF snapshots, synthesizes with the neutral style only, and exits 0/1.
- One process per job. Default bounds: queue of at most 4 outstanding jobs
  (1 running), 1000-character text, speed 0.75-1.5, 180-second timeout,
  taskkill tree kill on cancel or shutdown, no continuing compute afterwards.
- Jobs are identified by UUID only. Responses never contain filesystem paths,
  commands or text. Failed and cancelled jobs are reported with generic
  errors; subprocess output is discarded, never logged or returned.
- Generated audio lives in a per-job private temp directory. Failed or
  cancelled jobs are deleted immediately; completed jobs retain only
  speech.wav. Text is cleared from memory once the job leaves the queue.

## Provisioning (one-time, offline afterwards)

Provisioning copies already-verified public artifacts from the spike workspace
into `data/openvoice-runtime` (git-ignored), verifies every hash and records a
manifest. It never copies a virtualenv and never downloads anything.

```bash
python scripts/provision_openvoice.py \
  --source "C:/Users/Chris/AppData/Local/Temp/voicefont-openvoice-spike" \
  --reuse-python "C:/Users/Chris/AppData/Local/Temp/voicefont-openvoice-spike/.venv/Scripts/python.exe"
```

The spike venv keeps its absolute Python executable; venvs are not relocatable,
so the runtime references it explicitly in `config.json` instead of copying.
Alternative: recreate a fresh Python 3.10 venv from the pinned
`requirements-frozen.txt` (saved in `data/openvoice-runtime/provenance/`) and
pass that executable with `--reuse-python`. Do not blind-copy a venv.

For an already promoted bundle, a durable environment can be recreated explicitly
with the following Windows native-path commands (package installation needs
network or a populated uv cache; this recipe has not been exercised here):

```bash
uv venv --python "C:/Users/Chris/AppData/Local/Programs/Python/Python310/python.exe" data/openvoice-runtime/.venv
uv pip sync --python data/openvoice-runtime/.venv/Scripts/python.exe \
  --extra-index-url https://download.pytorch.org/whl/cpu \
  data/openvoice-runtime/provenance/requirements-frozen.txt
```

Then set the config's `python` field to the new absolute executable and run the
heavy offline test before relying on it. The installed configuration currently
reuses the original spike interpreter explicitly; deleting that spike venv will
make capability unavailable. Public assets, source, cached tokenizers, NLTK data,
source notices and manifests are already durable in the project data directory.

A fresh machine: re-run the documented spike download steps once (public
packages, pinned HF files, NLTK resource), then provision. Downloads happen
only during provisioning, never during serving; the worker fails closed on
missing or hash-mismatched resources.

Config is discovered from `VOICEFONT_OPENVOICE_CONFIG`, defaulting to
`data/openvoice-runtime/config.json`. The file contains only local paths, no
credentials. Override the path with the environment variable when needed.
Delete `data/openvoice-runtime` to remove the runtime completely.

## Capability and routes

- `GET /synthesis/capabilities` reports availability by validating the config
  and runtime manifest (no subprocess spawn). Unavailable reports a generic
  message with no paths.
- `POST /synthesis/jobs` `{voice_id, text, style:'neutral', speed}` accepts,
  validates text/speed/style, verifies profile consent and reference integrity
  first, and returns 202 `{id,status,audio_url?}` or 429 when bounded full.
- `GET /synthesis/jobs/{id}`, `POST /synthesis/jobs/{id}/cancel`,
  `GET /synthesis/jobs/{id}/audio` (200 WAV only when completed, otherwise
  409). Same-origin only; job IDs are validated UUIDs; unknown IDs are 404.

## How the parent enables synthesis

In `api.py` (parent-owned), after the profile store exists:

```python
from .synthesis_routes import create_synthesis_router

app.include_router(create_synthesis_router(store.root))
```

Then serve the bundled UI from the same origin. Preserve the router's lifespan
by using `app.include_router`. Health can call `synthesis_capabilities()` (also
exported as `capabilities`). Availability means configured resources exist and
sizes match, not a successful neural health probe; worker startup checks hashes.

The parent still needs to replace its unconditional `/speak` 503. Retain the
router instance, then have that compatibility endpoint accept `SpeechRequest`
and return `invoke(router.synthesis_service.submit, **body.model_dump())` with
status 202. This is the same bounded asynchronous job flow, not a second service.
Do not create an additional router/service per request. The canonical WAV download
remains `audio_url` returned on completion. Never call technical-fixture mode
from an HTTP endpoint.

The router owns its lifespan: on shutdown it cancels running work, joins the
coordinator thread and deletes all private job files. Tests use
`TestClient(create_synthesis_router(root, service=service))`-equivalent wiring
with a mocked backend for failure/cancel paths, plus one opt-in heavy test:

```bash
VOICEFONT_RUN_OPENVOICE_TEST=1 python -m pytest tests/test_synthesis.py -q
```

## Licensing and consent boundaries

OpenVoice and MeloTTS (code and models) declare MIT; BERT base uncased is
Apache-2.0. Preserve notices; `provenance/` retains upstream manifests and
license metadata. The reference `example_reference.mp3` is the official
repository fixture. No independent speaker release was verified; it is
restricted to technical verification and is never exposed through the HTTP
router, never enrolled as a voice, and never used to imitate anyone. User
profiles synthesize only their own consented, integrity-checked reference.
