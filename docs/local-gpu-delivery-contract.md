# Local GPU showcase acceptance contract

The target is real local deployment, not simulated infrastructure. This contract extends the native React product; it does not relabel earlier feature-autoencoder training as TTS training.

## Required evidence

1. Train or fine-tune a licensed text-to-speech model on authorized speech plus transcripts, using CUDA tensors and measured GPU memory. Record a changed checkpoint, train/validation losses, audio before/after, a bounded sweep with fixed heldout data, hyperparameters, provenance and model versions in local MLflow. Generated tones are not training speech. Tiny smoke runs prove mechanics, not model quality.
2. Serve a supported speech model/component on real NVIDIA Triton in local Kubernetes. Verify direct-vs-served parity, readiness, resource bounds, restart, load and rollback. Actual neural computation must use CUDA with no silent CPU fallback.
3. Extend LangGraph into dataset validation -> preprocess -> train -> evaluate -> register -> deploy -> verify, with rejected candidates unable to replace the last accepted deployment. Workflow orchestration is not automatically an autonomous LLM agent.
4. Use licensed pretrained speaker embeddings and self-hosted Weaviate with vectorizer disabled. Version embeddings, enforce consent, measure multi-recording retrieval and latency; self-match is insufficient.
5. Apply Terraform locally: bounded project namespace, storage, deployment/service resources and local registry integration. Never create GKE, GCS or Google Artifact Registry resources. Local equivalents are explicitly not those managed services.
6. Keep the React recording/calibration workspace, using the GameTheory paper/charcoal/gold style. Make new capabilities understandable and usable, with honest unavailable states.
7. Run local tests only. Explicit provisioning may download free public packages/models/images, preserving licenses and pinned provenance. Runtime must not fetch assets remotely. No personal recordings or weights in Git.

## Machine constraints

Observed RTX 3050 Laptop GPU, 6144 MiB VRAM; Windows driver 592.82 reports CUDA compatibility 13.1. A driver banner is not proof of framework CUDA execution. Docker Desktop Linux engine and Ubuntu WSL2 are running. Ubuntu currently sees 7.6 GiB RAM and 2 GiB swap. No kubectl contexts exist at intake. Do not change unrelated containers, global kube contexts, drivers or host resource settings without approval.

One physical GPU cannot become additional physical GPU nodes through software. Prove real local pod autoscaling and capacity limits. A simulated node is test evidence only, not a real provisioned GPU node. Hardware expansion remains external to software completion.

## Ownership during implementation

- Parent: core API/React integration, cross-module contracts, final gates and commits.
- Infrastructure: infra/**, scripts/local_cluster*, tests/test_local_cluster*, docs/local-cluster.md. Dedicated VoiceFont cluster only; no unrelated resources.
- Speech training: training/**, scripts/tts_*, tests/test_tts_*, docs/tts-training.md. Isolated environment and one bounded GPU job at a time.
- Embeddings: src/voicefont/embeddings.py, src/voicefont/vector_store.py, scripts/embedding_*, tests/test_embeddings*, tests/test_vector_store*, docs/embedding-search.md. No shared frontend/backend router edits.

Do not infer success from config files or test doubles. Save command results and machine-readable evidence under git-ignored data/. Final report must distinguish passed, blocked and unverified acceptance gates.
