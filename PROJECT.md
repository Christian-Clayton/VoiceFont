# VoiceFont: local voice ownership and ML engineering

**Status: development plan, not an implementation report.** This document defines the target. Check source, tests, and recorded execution evidence before claiming any capability works. All phases below are planned acceptance gates, not completed milestones.

**Audience:** contributors and reviewers who know Python but have not seen VoiceFont. **Document type:** explanation and roadmap. For phase entry gates start with [Phase 0](phase-0.md); for evidence rules use [validation](docs/planning/validation.md).

## Product goal

Capture an owner's voice through a guided local calibration session, preserve the recordings in an inspectable, versioned profile, and eventually let a local assistant speak through a replaceable speech engine. Demonstrate real machine learning and reproducible model operations on the same data without confusing an acoustic experiment with voice cloning.

The voice profile is the durable asset. A profile is not a universal executable voice font. Raw audio and provenance can transfer between engines; model-specific embeddings and behavior cannot be assumed compatible.

## Non-negotiable constraints

- No paid or cloud runtime, testing, tracking, storage, deployment, vectorization, transcription, or language-model APIs. No cloud free tiers either.
- Runtime and tests must work offline after explicit provisioning of free dependencies, images, language resources, and permitted weights. No implicit downloads or telemetry. Provisioning is a separate, user-approved step.
- Native Windows with Python 3.11 and CPU is the baseline. Docker, Kubernetes, and GPU support must not gate that baseline.
- Optional local Linux/WSL acceleration targets the available RTX 3050 with 6 GB VRAM. Fit must be measured, not inferred from a GPU being present. Start with batch size one and one model worker.
- Docker is installed but its engine was reported unavailable at planning intake. Container execution remains blocked until a real readiness check passes; do not substitute fabricated results.
- Use only owned or explicitly authorized recordings. Record consent and permitted uses before enrollment, training, search indexing, or synthesis. A consent record is not identity verification.
- Preserve original recordings byte-for-byte. Derived files are separate and reproducible. Never commit personal recordings, profiles, or private model artifacts by default.
- Local endpoints bind to loopback. No public ingress, hosted CI tests, hosted dashboards, cloud credentials, or unattended deployment.

## Two deliberately separate model paths

### Trainable acoustic representation baseline

Train a small acoustic feature autoencoder locally. It reconstructs acoustic representations, produces a versioned checkpoint, and yields embeddings for experimental similarity search. Evaluate held-out reconstruction loss against an untrained model and a train-set mean predictor. Preserve recording-level split membership and preprocessing provenance.

**This is genuine ML training, not text-to-speech (TTS), not voice cloning, and not speaker authentication.** A waveform-shaped test fixture, beep, or tone generator must never be presented as synthesized speech. Synthetic fixtures are permitted only when labeled for plumbing or numerical tests; speech-quality claims require authorized speech recordings.

### Reference-based speech synthesis

OpenVoice V2 is the initial model-dependent backend candidate. Its workflow uses reference audio and tone-color conversion with a separately provisioned compatible base TTS system. It is not a fine-tuning stage for a personal voice checkpoint. Pin and verify the upstream implementation, base TTS, converter, tokenizers, language resources, weights, and licenses together before integration.

Absent weights or incompatible environments must produce an explicit unavailable capability. No silent fallback to a fake voice. Reference style does not guarantee controllable emotion, accent fidelity, or rhythm; these need listening evidence.

## Technology choices with jobs to do

| Component | Earned purpose | Local execution and boundary |
|---|---|---|
| Python / NumPy / scikit-learn | Audio validation, feature extraction, trainable autoencoder | Native CPU baseline; PyTorch/ONNX export is a later optional serving experiment |
| LangGraph | Typed preprocess -> train -> evaluate -> deploy state machine | Local deterministic workflow, no LLM or LangSmith dependency |
| MLflow | Parameters, loss curves, artifact hashes, evaluation and run lineage | Local filesystem artifacts and local tracking backend; optional loopback UI |
| FastAPI and local client | Profile discovery, capabilities, analysis and eventual synthesis | Loopback API; no engine import required for native analysis |
| Weaviate | Filterable search over explicitly supplied voice/acoustic vectors | Optional self-hosted service; vectorizer disabled; native exact-search baseline remains available |
| Triton Inference Server | Serve the exported acoustic model and measure inference parity | Optional local Linux container, CPU first; not presumed to serve the whole OpenVoice pipeline |
| Docker Compose | Reproduce optional local service dependencies | Separate service profiles; images provisioned before offline tests |
| Kubernetes / Helm | Lifecycle, bounded training Jobs, health checks, persistence and rollback | Optional local kind or minikube CPU cluster |
| Terraform | Demonstrate declarative local namespace, storage and release management | Kubernetes/Helm providers against an existing local context; local state only |
| Prometheus / Grafana | Inspect latency, failures, queues and resource use | Optional local dashboards without telemetry or external assets |
| Ollama | Optional future local text-producing client example | Excluded from the baseline; add only if a concrete feature warrants memory and licensing costs |

Terraform must not create GKE, Google/AWS resources, managed vector services, external buckets, or registries. Cluster creation belongs to an explicit local kind/minikube setup step. Terraform owns a bounded project namespace, not the host or an arbitrary kubeconfig context.

## Target data flow

```text
Owned recordings + consent
  -> immutable local archive -> validated profile and dataset manifest
  -> preprocess -> train acoustic model -> evaluate -> promotion decision
                        | MLflow local evidence         |
                        +-------------------------------+
  -> local versioned model registry -> native inference
                                   -> optional ONNX/Triton serving
  -> model-versioned vectors -> native exact search / optional Weaviate

Calibration UI -> same archive/profile boundary
Local assistant text -> loopback API -> permitted profile
                                    -> provisioned OpenVoice V2 + base TTS
                                    -> actual speech -> client playback
```

The graph's initial `deploy` operation promotes a validated artifact to a local registry. It does not mean cloud deployment, Kubernetes installation, speech synthesis, or automatic release. Failed evaluation leaves the previous active model unchanged.

## Phase roadmap

| Phase | Deliverable | Dependencies | Exit evidence |
|---|---|---|---|
| [0](phase-0.md) | Scope, preservation, contracts and offline gates | None | Archive manifest, requirements mapping and documented readiness |
| [1](phase-1.md) | Native audio and portable profile core | 0 | Local CLI round-trip with rejected bad inputs and unchanged raw files |
| [2](phase-2.md) | Actual ML baseline, LangGraph and MLflow | 1 | Real weight updates, held-out metrics, graph failure and recovery evidence |
| [3](phase-3.md) | Fixed calibration and loopback service | 1 | Browser recording through restart-safe session to profile |
| [4](phase-4.md) | Adaptive calibration and versioned voice search | 2 and 3 | Auditable stop decisions and reproducible nearest-neighbor rankings |
| [5](phase-5.md) | Real OpenVoice backend and local assistant client | 1 and 3; model provisioning gate | Actual intelligible speech with honest listening and latency report |
| [6](phase-6.md) | Multi-style reference workflows | 3 and 5 | At least three reference styles and evaluated same-text outputs |
| [7](phase-7.md) | Optional local MLOps service and deployment showcase | 2 and 4; working local engine | Compose, Triton parity, Helm lifecycle and local-only Terraform evidence |
| [8](phase-8.md) | Optional sentence streaming and evidence-based release | See phase-specific gates | Offline replay, portability, recovery and truthful capability matrix |

Phase numbers are reading order, not a requirement to serialize all work. Phase 3 can proceed alongside Phase 2 after profile contracts settle. Model provisioning and feasibility for Phase 5 should be investigated early without blocking the native ML path. See [sequencing](docs/planning/sequencing.md).

## Checkable project success

- [ ] A clean, explicitly provisioned Windows CPU environment validates audio, builds and relocates a profile, trains a real acoustic model, evaluates held-out loss, and uses its checkpoint without Docker or internet access.
- [ ] The LangGraph run records preprocess, train, evaluate and local deployment outcomes in MLflow, including a deliberately rejected candidate and a recovered interrupted run.
- [ ] Calibration preserves every take and distinguishes intended prompt coverage from measured signal evidence.
- [ ] Search ranks vectors only within the same embedding space and excludes revoked profiles. Relevance is evaluated rather than asserted from self-match alone.
- [ ] The separately provisioned speech backend produces intelligible new text from an authorized reference. Human ratings report resemblance and limitations without claiming identity proof.
- [ ] Optional service deployments pass their own offline integration gates. Native success alone does not claim Triton, Weaviate, Docker, Kubernetes, or Terraform execution.
- [ ] Personal data stays private; backup/restore and consent withdrawal are exercised on disposable fixtures.

## Scope and history

Preserved goals include calibration, adaptive prompt selection, expressive range, local clients, multi-style references, streaming, portability, and documentation. New ML operations support these assets instead of replacing them with unrelated infrastructure.

Out of scope: cloud resources, paid services, multi-user hosting, marketplaces, covert impersonation, real-time voice conversion, custom TTS fine-tuning, unvalidated biometric inference, and unrelated cognitive-organism or world-model research.

Exact original plans and the unchanged conversation are preserved under [archive](docs/planning/archive/). Read the [revision record](docs/planning/revision-record.md) before reusing archived snippets. Archived commands and checked boxes are historical text, not current instructions or evidence.
