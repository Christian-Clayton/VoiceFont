#!/bin/bash
# Deploy Triton Inference Server + Weaviate to local k3d cluster.
set -euo pipefail

CLUSTER_NAME="voicefont-local"
kubectl config use-context "k3d-${CLUSTER_NAME}" 2>/dev/null || true

# Create namespace
kubectl apply -f "$(dirname "$0")/../k8s/namespace.yaml"

# Deploy local storage
kubectl apply -f "$(dirname "$0")/../k8s/storage.yaml"

# Deploy Weaviate (CPU)
kubectl apply -f "$(dirname "$0")/../k8s/weaviate.yaml"

# Deploy Triton (GPU)
kubectl apply -f "$(dirname "$0")/../k8s/triton.yaml"

# Deploy VoiceFont app
kubectl apply -f "$(dirname "$0")/../k8s/voicefont.yaml"

echo "Waiting for pods..."
kubectl wait --for=condition=ready pod -l app=weaviate -n voicefont --timeout=120s
kubectl wait --for=condition=ready pod -l app=triton -n voicefont --timeout=120s
kubectl wait --for=condition=ready pod -l app=voicefont -n voicefont --timeout=120s

echo "Deployment complete."
kubectl get pods -n voicefont
kubectl get svc -n voicefont
