# Sequence work by proven dependencies

**Document type:** planning explanation for contributors and the project owner. **Status:** proposed schedule, no delivery date committed. [PROJECT.md](../../PROJECT.md) defines the product and numbered gates.

The first usable slice is Phase 1's authorized WAV -> quality report -> portable profile. The first ML slice is Phase 2's real CPU optimizer/checkpoint/held-out evaluation. Container readiness and OpenVoice provisioning are not prerequisites for either.

## Dependency network

```text
0 contracts
  -> 1 native profiles
       -> 2 real ML + LangGraph + MLflow -----------> 7 local infrastructure
       -> 3 fixed calibration -----> 4 adaptive/search ----^
                    |                    ^
                    |                    | 2 learned vector contract
                    v
               5 real speech -> 6 styles
                    |
                    v
               8 optional streaming

8 release gates gather evidence from only the tracks being claimed.
5 provisioning feasibility can be investigated after 0, before 3 finishes.
```

At task level, Phase 4 adaptive selection depends on Phase 3, while learned-vector search depends on Phase 2. Parallel owners must agree on profile IDs, hashes, artifact versions and accepted-take events first. Do not have two agents edit the same schema or deployment files concurrently. The parent assigns code ownership and owns git operations; the documentation worker owns only PROJECT.md, phase-0 through phase-8 and docs/planning.

## Critical paths and gates

| Deliverable | Technical chain | Main uncertainty | What can proceed independently |
|---|---|---|---|
| Native ML showcase | 0 -> 1 -> 2 -> native release review | Real training/evaluation reproducibility and independent data | Calibration UI and model provisioning spike |
| Calibrated search workflow | 0 -> 1 -> max(2, 3) -> 4 -> review | Accepted-take evidence and representation usefulness | Speech backend feasibility |
| Voice assistant | 0 -> 1 -> 3 -> 5 -> 6 -> speech release review | Free offline base TTS/converter compatibility and actual quality | Acoustic model serving showcase |
| Local MLOps showcase | 0 -> 1 -> max(2, 3) -> 4 -> 7 -> review | Docker/WSL readiness, export parity and local resource limits | Real speech and style evaluation |
| Optional streaming | 5 -> 8.1 -> 8.2 -> 8.3 | Model granularity, framing and cancellation | Kubernetes is not needed |

There is no defensible single calendar critical path before resource availability and scope selection. For the requested first ML deliverable, 0 -> 1 -> 2 is the controlling chain. For the full combined showcase, the longer of the speech and infrastructure branches controls completion. A single developer cannot realize all apparent parallelism; concurrent agents do not eliminate review or shared-hardware contention.

## Effort ranges, not a promised deadline

Inside-view estimates below are focused contributor-days, optimistic / most likely / pessimistic. They include tests and documentation for the slice, but exclude waiting for user recordings, license approvals, hardware changes and unknown upstream breakage. They are provisional assumptions, not measured productivity. Re-estimate after the first two implemented slices. There are no three comparable completed projects in the supplied materials for an outside-view calibration.

| Slice | O / M / P days | Evidence that retires uncertainty |
|---|---|---|
| First native WAV/profile round-trip | 1 / 3 / 6 | Offline CLI and relocation tests |
| Real acoustic model + held-out evaluation | 2 / 5 / 10 | Checkpoint reload, baseline comparison and leakage checks |
| Graph/tracking/promotion recovery | 2 / 4 / 8 | Real MLflow records and interrupted/rejected run replay |
| Fixed browser calibration | 3 / 7 / 14 | Real microphone session plus restart/re-record tests |
| Adaptive policy and native search | 2 / 5 / 10 | Replay and relevance report |
| OpenVoice feasibility investigation | 1 / 2 / 4 | Pinned free local workflow succeeds or specific blocker recorded |
| Speech service/client after feasibility | 2 / 5 / 10 | Actual speech and local client integration |
| Multi-style recording/evaluation | 2 / 4 / 8 | Same-text listening comparisons |
| Compose, ONNX and Triton | 3 / 7 / 14 | Real local service parity and restart evidence |
| Local Helm/Terraform lifecycle | 3 / 6 / 12 | Apply/no-op/rollback/teardown evidence |
| Optional sentence streaming | 3 / 7 / 15 | Framing, first-audio and cancellation evidence |
| Selected-track release review/replay | 2 / 4 / 8 | Clean offline replay and capability matrix |

Do not sum these into the original 3-5 week promise. No project completion-date distribution is asserted here. Before committing to a full schedule, run a task-network Monte Carlo simulation using measured slice estimates, available people, shared GPU/CPU capacity and correlated platform risks; report median and 90th-percentile outcomes rather than a sum of means. This is a planning requirement, not an experiment performed by this documentation revision.

Concentrate contingency after the OpenVoice feasibility investigation and container/export checks. Stop each investigation at its agreed time bound and record a blocker. Do not consume the native milestone's time repeatedly retrying optional services.

## Decision and fallback register

| Decision / owner | Recommendation | Trigger to reconsider |
|---|---|---|
| Core environment / implementation lead | Native Python 3.11 CPU, isolated extras | A pinned required package lacks supported Windows build |
| Speech environment / owner plus backend lead | Separate local Linux/WSL environment if needed | Weight/license or dependency mismatch; never paid API fallback |
| Cluster / owner | kind CPU first; minikube alternative | Actual host compatibility failure |
| MLflow backend / pipeline lead | Supported local store and local artifacts | Pinned version deprecates or rejects selected storage semantics |
| Embedding usefulness / ML lead | Reconstruction baseline with honest acoustic label | Independent-query retrieval fails to beat a simple baseline |
| Style/streaming / owner | Keep optional until tested benefit exists | Real listening or latency comparison shows no value |
| Destructive changes / owner | Explicit approval, disposable tests and backup | Schema migration, withdrawal deletion, deploy edits, apply/destroy |

Runtime paths in phase tables are proposed responsibilities. During implementation, reconcile them with the real source tree and keep usage documentation tied to executed commands. Plans must not force duplicate modules merely to match an illustrative path.
