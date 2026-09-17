# Phase 7: optional local MLOps deployment showcase

**Status: planned, local-service dependent.** Implementation specification after [Phase 2](phase-2.md) trained artifacts and [Phase 4](phase-4.md) search contracts. The native CPU deliverable must continue working independently.

## Outcome and readiness

Reproduce local tracking/search services, serve the real exported acoustic model through Triton, and demonstrate local Kubernetes lifecycle management with Helm and Terraform. These tools operate on already-working ML artifacts, not empty containers or a pretend voice model.

At planning intake Docker was installed but its engine was reported unavailable. Validate a real local engine before any service execution claim. Kubernetes and Linux containers may require WSL2 or another supported local setup. Do not promise GPU passthrough in kind or minikube on Windows. CPU containers and a CPU local cluster are the required service acceptance target; GPU is a separate optional experiment.

## Increments

| ID | Proposed files | Behavior change | Test first / verification | Dependency and risk |
|---|---|---|---|---|
| 7.1 | Compose/Dockerfiles, service configuration tests | Start optional MLflow and Weaviate with private persistent local storage | Health/readiness, restart persistence and offline startup tested against real services | Phases 2/4 plus running engine; owner approval before deploy config changes |
| 7.2 | Model export, ONNX parity tests | Export the learned acoustic encoder/decoder with exact preprocessing contract | Native and ONNX output shapes/values agree within predeclared tolerance on held-out inputs | Phase 2; exportability must be tested before Triton packaging |
| 7.3 | Triton model repository/config, inference integration tests | Serve that exported model using local CPU Triton | Real inference agrees with native result; corrupt/missing version fails readiness | 7.2 and engine; OpenVoice is not automatically Triton-compatible |
| 7.4 | Helm chart, training Job and chart tests | Install optional services and bounded training Job into local cluster | Render validation followed by actual install, inference, persistence, upgrade and rollback | 7.1/7.3; start one replica, no imaginary GPU capacity |
| 7.5 | Local Terraform configuration and plan checks | Declare namespace/resources and Helm release using local providers | Plan rejects non-local context; actual apply, second no-op plan and scoped destroy recorded | 7.4; local state and approved resource ownership only |
| 7.6 | Local metrics dashboards and recovery tests | Inspect queue, latency, failures, training lineage and resources | Known request/failure changes matching metrics; backup/restore preserves artifact hashes | 7.5; no hosted dashboards, external fonts or telemetry |

## Offline and resource contract

Provision free base images, chart dependencies, Terraform providers and model weights explicitly before offline execution. Pin versions/digests and license provenance. Build using a local wheelhouse/cache where possible and test without internet. Do not pull images during acceptance tests. Keep training, inference and auxiliary services separately selectable; avoid loading all stacks at once on a small machine.

Raw data mounts are read-only. Artifacts and tracking stores have explicit local writable volumes. Do not mount the host Docker socket into application containers. Bind published ports to loopback. Default to no ingress and no external LoadBalancer. Prefer local port-forwarding for demos. Bound CPU, memory, job duration, concurrency, log retention and storage use. PVC lifecycle must not silently destroy personal recordings.

Choose kind as the first CPU cluster target; minikube is an alternative if host compatibility warrants it. Create the local cluster explicitly outside Terraform. Load provisioned images into that cluster, and validate its identity before changes. Terraform uses only local state plus Kubernetes/Helm providers against that existing cluster. No Google/AWS providers, GKE, cloud credentials, managed vector service, remote backend, cloud buckets, public registry publishing or billable resources.

Helm owns Kubernetes objects within its release. Terraform may own the namespace and Helm release but must not also manage the same rendered objects directly. Do not import or destroy unrelated local resources. Require user review before apply/destroy or deployment configuration edits.

Autoscaling is deferred until queue metrics and resource measurements justify it. A single 6 GB GPU cannot become several independent GPUs through replicas. Optional HPA or scheduling demonstrations must disclose local capacity and prove bounded behavior; fractional GPU and time-sharing are not baseline promises.

## Acceptance criteria

- [ ] Compose starts real local services with internet unavailable and retains tracking/search data across restart. Native tests still pass with every service stopped.
- [ ] Held-out native, ONNX and Triton outputs agree within a documented tolerance, including batch and invalid-shape tests. Evidence includes actual model checksum and server version.
- [ ] A local CPU cluster runs the real training Job and inference. Helm install, upgrade/rollback and uninstall behavior are exercised with disposable fixtures.
- [ ] Terraform validation and plan use only local Kubernetes/Helm resources. Apply succeeds, a second plan has no changes, and approved scoped teardown leaves raw archives intact.
- [ ] Metrics report actual request durations and failures; resource measurements describe the tested host, not theoretical GPU speedups.
- [ ] Offline startup, service failure and restore are tested. Blocked engine/GPU checks remain explicitly blocked, not checked off from manifest rendering.

**Not included:** cloud deployment, hosted CI/CD, automatic push-to-production, OpenVoice-to-ONNX promises, public service exposure or required GPU Kubernetes. Release documentation in [Phase 8](phase-8.md) distinguishes static validation from actual service execution.
