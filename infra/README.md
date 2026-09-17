# Local Kubernetes + Triton + Weaviate deployment

This configures local k3d Kubernetes with GPU support, Triton Inference Server
for model serving, and Weaviate for vector search.

## Prerequisites

- Docker Desktop with WSL2 (already installed)
- NVIDIA Container Toolkit for GPU passthrough to k3s
- k3d.exe in data/cluster-tools/
- voicefont-k3s:cuda12.4-v1.31.5 image built

## Architecture

```
┌─────────────────────────────────────────────┐
│  Windows Host (RTX 3050 6GB)                │
│  ┌─────────────────────────────────────────┐│
│  │ k3d cluster (voicefont-local)           ││
│  │ ┌───────────┐ ┌──────────┐ ┌──────────┐││
│  │ │  Triton    │ │ Weaviate │ │ VoiceFont│││
│  │ │  (GPU)     │ │ (CPU)    │ │ (FastAPI)│││
│  │ │ :8000-8002 │ │ :18080   │ │ :8000    │││
│  │ └───────────┘ └──────────┘ └──────────┘││
│  └─────────────────────────────────────────┘│
│  localhost:30080 → VoiceFont UI              │
│  localhost:30081 → Triton HTTP               │
│  localhost:30082 → Weaviate                  │
└─────────────────────────────────────────────┘
```

## GPU access flow
NVIDIA host driver → nvidia-container-toolkit → k3s container (--gpus all) → Triton pod
