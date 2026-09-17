# CUDA-capable k3s node, based on k3d's documented custom-node approach.
# Provisioning downloads packages; running the node does not install anything.
FROM rancher/k3s:v1.31.5-k3s1 AS k3s
FROM nvidia/cuda:12.4.1-base-ubuntu22.04
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl gnupg \
    && curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg \
    && printf '%s\n' 'deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://nvidia.github.io/libnvidia-container/stable/deb/amd64 /' > /etc/apt/sources.list.d/nvidia-container-toolkit.list \
    && apt-get update && apt-get install -y --no-install-recommends nvidia-container-toolkit \
    && rm -rf /var/lib/apt/lists/*
COPY --from=k3s /bin/ /bin/
COPY --from=k3s /etc/ /etc/
COPY --from=k3s /usr/ /usr/
ENV PATH="${PATH}:/bin/aux"
ENTRYPOINT ["/bin/k3s"]
CMD ["agent"]
