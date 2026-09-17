# VoiceFont Cloud

> Train, deploy, and serve custom voice models with full MLOps

## Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Orchestration** | LangGraph | Voice cloning pipeline: preprocess → train → evaluate → deploy |
| **Serving** | Triton Inference Server (K8s) | GPU-accelerated model inference |
| **Experiment Tracking** | MLflow | Loss curves, audio samples, hyperparameter sweeps |
| **Infrastructure** | Terraform | GKE cluster, GPU node pool, Cloud Storage, Artifact Registry |
| **Vector DB** | Weaviate | Voice embeddings for similarity search |
| **Container Orchestration** | Kubernetes (Helm) | Auto-scaling GPU workers, model serving |

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        CLI / API                             │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     LangGraph Pipeline                       │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌─────────┐ │
│  │Preprocess│──▶│  Train   │──▶│ Evaluate │──▶│ Deploy  │ │
│  └──────────┘   └──────────┘   └──────────┘   └─────────┘ │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Kubernetes Cluster                        │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────┐ │
│  │ Training Worker │  │ Triton Serving  │  │  Weaviate   │ │
│  │ (GPU Node Pool) │  │ (GPU Node Pool) │  │  (CPU Pool) │ │
│  └─────────────────┘  └─────────────────┘  └─────────────┘ │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     Object Storage                           │
│  Cloud Storage: datasets / model artifacts / audio samples   │
└─────────────────────────────────────────────────────────────┘
```

## Phases

### Phase 1: Containerize
- Dockerize VoiceFont training and inference
- Docker Compose for local development (Ollama + Weaviate + MLflow)
- Verify training pipeline runs in container

### Phase 2: Kubernetes Local Deploy
- Helm chart for VoiceFont services
- kind/minikube cluster with GPU support
- Deploy MLflow + Weaviate + Triton
- K8s manifests for training jobs (Job/CronJob)

### Phase 3: LangGraph Pipeline
- Implement pipeline as LangGraph nodes:
  - `preprocess_node`: Clean audio, extract features
  - `train_node`: Fine-tune voice model
  - `evaluate_node`: Generate test samples, compute metrics
  - `deploy_node`: Push to Triton, update serving config
- Each node logs to MLflow

### Phase 4: Terraform
- Provision GKE cluster with GPU node pool
- Cloud Storage buckets for datasets and models
- Artifact Registry for Docker images
- Weaviate Cloud or self-managed on GKE

### Phase 5: Voice Similarity Search
- Extract voice embeddings during training
- Store in Weaviate with metadata (language, gender, style)
- API endpoint: "find voices similar to this"
- CLI command: `voicefont search --reference audio.wav`

### Phase 6: Production Polish
- HPA for inference (scale based on request queue)
- GPU time-sharing / fractional GPU for cost savings
- Monitoring: Prometheus + Grafana for model latency, GPU usage
- CI/CD: GitHub Actions for deploy on push to main

## Voice Cloning Workflow

```
1. User uploads 10-30 minutes of reference audio
2. LangGraph preprocesses: split, clean, transcribe, extract embeddings
3. MLflow starts experiment: track hyperparameters, training loss
4. Training job runs on GPU node pool
5. Evaluation generates comparison samples
6. On success: deploy to Triton, register voice in Weaviate
7. User can now synthesize: "speak this text in cloned voice"
```

## Vector DB Schema (Weaviate)

```json
{
  "class": "Voice",
  "properties": [
    { "name": "voice_id", "dataType": ["string"] },
    { "name": "name", "dataType": ["string"] },
    { "name": "language", "dataType": ["string"] },
    { "name": "gender", "dataType": ["string"] },
    { "name": "style", "dataType": ["string"] },
    { "name": "embedding", "dataType": ["vector"] },
    { "name": "sample_url", "dataType": ["string"] },
    { "name": "created_at", "dataType": ["date"] }
  ],
  "vectorizer": "none"
}
```

## Files to Create

```
voice-font-cloud/
├── docker-compose.yml          # Local dev: Ollama + Weaviate + MLflow + Triton
├── Dockerfile.training         # Training container
├── Dockerfile.serving          # Triton serving container
├── helm/
│   ├── Chart.yaml
│   ├── values.yaml
│   └── templates/
│       ├── training-job.yaml
│       ├── triton-deployment.yaml
│       ├── weaviate-deployment.yaml
│       └── ingress.yaml
├── terraform/
│   ├── main.tf
│   ├── variables.tf
│   ├── gke.tf
│   └── outputs.tf
├── pipeline/
│   ├── __init__.py
│   ├── graph.py                # LangGraph definition
│   ├── nodes.py                # Pipeline nodes
│   └── state.py                # Shared state
├── scripts/
│   ├── verify_setup.py
│   └── deploy.sh
└── README.md
```

## Success Criteria

- [ ] Train a voice model locally in Docker
- [ ] Deploy to local K8s with `helm install voicefont ./helm`
- [ ] LangGraph pipeline runs end-to-end: preprocess → train → evaluate → deploy
- [ ] MLflow UI shows training metrics and audio samples
- [ ] Voice similarity search returns relevant matches
- [ ] Terraform provisions a working GKE cluster
- [ ] `voicefont search --reference voice.wav` returns similar voices
