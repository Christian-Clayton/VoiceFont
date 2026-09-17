# Planning revision record

**Document type:** historical reference for maintainers. **Scope:** documentation only. The revision replaces active plans with a local-only roadmap; it does not implement application features, execute application tests or create commits.

## Source preservation

Before rewriting, all originals were read fully in bounded batches. Exact bytes were copied to `archive/` and compared with the originals. [archive-manifest.json](archive-manifest.json) records filename, byte count, SHA-256 and complete read ranges. Ten plan files plus conversation.md are preserved. The root conversation.md is unchanged.

The archive is inert historical material, not active implementation instructions. Original formatting, incomplete code blocks, incorrect claims and cloud references remain unchanged intentionally. Do not apply archived snippets without current source review and tests.

## Findings that changed the plan

| Original source | Finding | Active-plan correction |
|---|---|---|
| PROJECT.md, technology and infrastructure sections | Cloud-first GKE, GPU node pools, storage/registry and managed vector options conflict with local ownership | Native CPU first; optional local services; existing kind/minikube cluster plus Kubernetes/Helm Terraform providers and local state |
| PROJECT.md, pipeline/workflow | Generic voice fine-tuning conflates training and reference cloning | Real acoustic representation training has its own evaluation; OpenVoice V2 remains separate reference-based synthesis |
| PROJECT.md, Weaviate schema | Embedding shown as an ordinary `vector` property | Explicit client-supplied vectors with vectorization disabled and model-versioned collections |
| phase-0.md and conversation.md | Portable profiles, raw data, calibration and local assistant are the durable product goals | Preserve these across all tracks instead of replacing them with infrastructure |
| phase-1.md | Guessed dependency/demo commands and advice to commit voice recordings | Verify pinned upstream workflow; keep private recordings out of git by default |
| phase-2.md | File ends at line 507 with `import numpy` inside an unfinished engine example | Replace incomplete executable-looking prose with testable implementation specifications |
| phase-3.md | Fixed corpus only partly specified; prompt tags counted as measured coverage; re-record/restart semantics incomplete | Complete versioned corpus increment, evidence labels and accepted-take event/persistence model |
| phase-4.md, lines 1022-1980 | Unrelated Policy Selection + Organism Core, Indra attention, cognitive workspace and neural-operator world-model material appended | Preserve exact appendix only in archive; exclude from active VoiceFont scope |
| phase-4.md, original adaptive section | Competing stop policies and predicted gain used as if measured | One stop policy; distinguish sufficient, plateau, cap and user stop; log observed accepted-take gain |
| phase-5.md | Placeholder AI and streaming stub alongside completion claims | Require real local model for AI claim; explicit capability unavailability; streaming later |
| phase-6.md | Style reference presence/hash/pitch difference could be mistaken for audible expressiveness | Require same-text real synthesis and listening evidence; keep availability distinct from capability |
| phase-7.md | Arbitrary transfer chunks treated as WAV units; early headers and full-buffer timing misrepresent first audio | Frame audio correctly; measure playable first sentence; disclose engine cancellation limits |
| phase-8.md | Prewritten README/changelog and checked boxes claim unexecuted work complete | Require execution-backed capability matrix and release per verified track |

The full read confirmed the unrelated appended research block in phase-4.md. It did not establish comparable appended blocks in every other phase; no broader contamination claim is needed. Other phase defects are listed specifically above.

## Requirement traceability

| Requirement | Active owner / gate |
|---|---|
| Owner consent, immutable raw recordings, portable profiles | Phases 0/1, lifecycle verification in 8 |
| Real locally trained ML with held-out metrics | Phase 2 |
| LangGraph preprocess/train/evaluate/deploy | Phase 2; deploy initially means local promotion |
| MLflow loss curves, parameters and artifact lineage | Phase 2; optional service packaging in 7 |
| Guided calibration and expressive coverage | Phase 3 |
| Adaptive prompts and early finish | Phase 4 with explicit evidence limitations |
| Voice similarity search and Weaviate | Phase 4; native exact baseline and explicit external vectors |
| Real OpenVoice V2 synthesis and assistant client | Phase 5; not fine-tuning |
| Multi-style references | Phase 6 |
| Triton, Docker, Kubernetes/Helm, local Terraform | Phase 7; actual execution required separately |
| Streaming and interruption | Optional Phase 8 increments 8.1-8.3 |
| Documentation, observability, reproducibility and release | Throughout; final gate in Phase 8 |
| No paid/cloud runtime or tests; offline after provisioning | PROJECT.md and validation protocol, applies to every phase |

## Writing and planning method

Read and applied `C:/Projects/.github/copilot-instructions.md`, `agents/planner.agent.md` and `agents/docs-writer.agent.md`. The planner pass established independently testable increments, dependencies, risks and approval gates. The docs-writer pass removed unverified usage claims and clearly separated planning from runtime reference material. Relevant scoping, sequencing, estimation, sequential-thinking and clear-writing skills informed the revision.

No application source, README, deployment configuration or another agent's files were edited by this revision. Proposed source paths are implementation responsibility suggestions, not created artifacts. The parent owns code work, deployment approvals and all git actions.

## Documentation validation

Validation results are recorded in [documentation-validation.json](documentation-validation.json). Checks cover archive hashes/byte counts, unchanged conversation, ten active plan files, linked local documents, unchecked acceptance lists, phase structure and no em dashes in authored material. This report is not application-test evidence. No Docker, GPU, model synthesis, Kubernetes or Terraform execution is claimed by the documentation worker.
