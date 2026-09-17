#!/bin/bash
# Create local k3d cluster with GPU support.
set -euo pipefail

CLUSTER_NAME="voicefont-local"
TOOLS_DIR="$(dirname "$0")/../../data/cluster-tools"

echo "Creating k3d cluster: ${CLUSTER_NAME}"

# Create cluster with 1 server + 1 GPU agent
"${TOOLS_DIR}/k3d.exe" cluster create "${CLUSTER_NAME}" \
  --image voicefont-k3s:cuda12.4-v1.31.5 \
  --servers 1 \
  --agents 1 \
  --gpus all \
  -p "30080:80@loadbalancer" \
  -p "30081:8000@loadbalancer" \
  -p "30082:8080@loadbalancer" \
  --k3s-arg "--disable=traefik@server:0" \
  --wait

echo "Cluster created."
echo "Verifying GPU access in cluster..."
kubectl get nodes
kubectl describe node | grep -A 3 "Capacity:" || true
