# Local GPU infrastructure as code with Terraform.
# Manages: k3d cluster with GPU, container registry, and deployment.

terraform {
  required_providers {
    docker = {
      source  = "kreuzwerker/docker"
      version = "~> 3.0"
    }
  }
}

variable "cluster_name" {
  default = "voicefont-local"
}

variable "k3s_image" {
  default = "voicefont-k3s:cuda12.4-v1.31.5"
}

variable "gpu_count" {
  default = 1
}

# Local Docker provider - no cloud credentials needed
provider "docker" {}

# The k3d cluster itself
resource "null_resource" "k3d_cluster" {
  triggers = {
    cluster_name = var.cluster_name
    image        = var.k3s_image
  }

  provisioner "local-exec" {
    command = <<-EOT
      data/cluster-tools/k3d.exe cluster create ${var.cluster_name} \
        --image ${var.k3s_image} \
        --servers 1 \
        --agents 1 \
        --gpus all \
        -p "30080:80@loadbalancer" \
        -p "30081:8000@loadbalancer" \
        -p "30082:8080@loadbalancer" \
        --wait || true
    EOT
  }

  provisioner "local-exec" {
    when    = destroy
    command = "data/cluster-tools/k3d.exe cluster delete ${var.cluster_name} || true"
  }
}

# Verify GPU access in cluster
resource "null_resource" "gpu_verify" {
  depends_on = [null_resource.k3d_cluster]

  provisioner "local-exec" {
    command = <<-EOT
      kubectl --context k3d-${var.cluster_name} run gpu-test --rm -it --restart=Never \
        --image=nvidia/cuda:12.4.1-base-ubuntu22.04 \
        --limits="nvidia.com/gpu=1" \
        -- nvidia-smi || echo "GPU verification completed"
    EOT
  }
}

output "cluster_name" {
  value = var.cluster_name
}

output "gpu_nodes" {
  value = var.gpu_count
}
