# VoiceFont

Local voice ownership and reproducible ML experiments. This is an early implementation, not a finished voice-cloning application.

## Working now

- PCM WAV validation, silence/clipping checks and deterministic acoustic descriptors.
- Consent-gated, versioned JSON profiles preserving the original audio and SHA256 provenance.
- Local cosine similarity search, CLI and loopback-only FastAPI service.
- A real scikit-learn bottleneck autoencoder with recording-group train/validation splits and train-only scaling.
- A real LangGraph preprocess -> train -> evaluate -> publish workflow with local MLflow SQLite tracking and filesystem artifacts.
- Conditional model registration: failed evaluation does not publish a candidate. Saved weights are NPZ, not pickle.

**Acoustic similarity is not speaker identification. Numeric reconstruction is not voice cloning.** The ML demonstration uses an explicitly synthetic numeric dataset, not recorded voices. Its trained representation is not yet connected to profile search. `/speak` returns HTTP 503 because a genuine speech backend is not installed in the application.

## Install and check

Audience: Python developers new to this repository. These are native Windows instructions; no Docker or GPU is needed. Use Python 3.11 and [uv](https://docs.astral.sh/uv/). Initial dependency provisioning uses free package downloads. Runtime uses no paid or cloud services.

From `C:\Projects\VoiceFont`:

```bash
uv sync --extra ml --extra dev
uv run --offline pytest -q
uv run --offline ruff check src tests scripts
uv build --wheel
```

`uv.lock` records the resolved dependency set. After provisioning, add `--frozen --offline` to `uv sync` for repeat installation from the local cache. `uv --offline` prevents package-manager downloads, not application network connections. The ML smoke was separately exercised with Python socket connection calls blocked; see [verification](docs/verification.md).

## Run the ML demonstration

```bash
uv run --offline python scripts/ml_demo.py
```

This creates `data/ml-demo/report.json`, a local SQLite tracking database and local model artifacts. The seeded low-rank numeric fixture is intentionally easy. It proves real training, held-out evaluation and workflow mechanics, not performance on speech. A convergence warning means the bounded optimizer reached its iteration limit, not that it converged.

For application integration:

```python
from voicefont.pipeline import run_pipeline
from voicefont.training import TrainingConfig

# features: finite numeric matrix. recording_ids: original recording ID per row.
# Keep all derived rows from one original recording under the same ID.
report = run_pipeline(
    features,
    recording_ids,
    output_dir="data/my-experiment",
    provenance="Describe the actual authorized dataset and its preparation",
    config=TrainingConfig(seed=7, bottleneck=2),
)
```

This API is a numeric experiment boundary. The caller is responsible for dataset permission and accurate grouping. Automated audio-dataset ingestion, persisted split manifests, resumable training and checkpoint loading remain roadmap work.

## Enroll and search an authorized recording

Provide your own or explicitly permitted PCM WAV. The current limit is 0.1-180 seconds, mono/stereo, 8-96 kHz, integer 8/16/24/32-bit samples, at most 50 MiB. Long calibration sessions will need separate takes.

```bash
uv run --offline voicefont enroll --reference "C:/path/to/authorized.wav" --voice-id my-voice --name "My voice" --consent
uv run --offline voicefont inspect --voice-id my-voice
uv run --offline voicefont search --reference "C:/path/to/authorized.wav" --top-k 5
uv run --offline voicefont list
uv run --offline voicefont serve
```

The recording path above is an example, not a supplied file. Enrollment is immutable: duplicate IDs fail rather than replacing originals. Search includes self-matches and uses fixed acoustic descriptors, not the trained autoencoder.

Profiles default to `~/.voicefont/profiles`. `--root` selects a different registry; `VOICEFONT_HOME` changes its parent. Keep profile directories private. Consent is a permission assertion, not identity verification. Revocation and deletion workflows are not yet implemented.

## HTTP API

The CLI binds to `127.0.0.1:8000`. `localhost` is normalized to IPv4 loopback; `::1` is currently unsupported. Access logging is disabled to avoid retaining profile names and IDs from request URLs. Custom ASGI launchers must use equivalent `access_log=False` settings. Do not expose this single-user unauthenticated service publicly. Browser origins are currently rejected; calibration UI is not built yet.

| Method | Route | Result |
|---|---|---|
| GET | `/health` | Readiness and unavailable synthesis flag |
| GET | `/profiles` | Stored profiles |
| GET | `/profiles/{voice_id}` | One validated profile |
| GET | `/profiles/{voice_id}/similar?top_k=5` | Similar acoustic profiles |
| POST | `/profiles?voice_id=my-voice&name=My%20voice&consent=true` | Enroll raw WAV body |
| POST | `/search?top_k=5` | Search raw WAV body |
| POST | `/speak` | 503: genuine synthesis unavailable |

WAV requests use `Content-Type: audio/wav`. HTTP callers cannot select server filesystem paths or remote URLs. Local disk is owner-trusted. Profile listing currently verifies all stored references and is designed for a small personal registry, not large-scale serving.

## Roadmap, not completion claims

See [PROJECT.md](PROJECT.md), [phase-0.md](phase-0.md) and [sequencing](docs/planning/sequencing.md). Calibration, adaptive prompting, real OpenVoice integration, multi-style synthesis, Weaviate, Triton, Docker deployment, Kubernetes/Helm, local Terraform and streaming are planned, not delivered by the native baseline.

Original documents are preserved byte-for-byte in `docs/planning/archive/` with a hash manifest. Historical snippets are not current instructions. Private voice data, generated models, tracking databases, virtual environments and build output are excluded from Git.
