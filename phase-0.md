# Phase 0: contracts and evidence before implementation

**Status: planned gate.** This is a planning reference for implementers, not an assertion of completed setup. [PROJECT.md](PROJECT.md) controls scope; [validation](docs/planning/validation.md) controls evidence.

## Outcome and dependencies

Make the first native experiment possible without losing the original design or introducing a cloud dependency. No prerequisite phase. Phase 1 starts after the preservation, consent, data-boundary and interpreter gates are settled. The earliest useful vertical slice is an authorized WAV -> validated report -> relocatable profile, followed immediately by real local ML training.

## Increments

| ID | Proposed files / boundary | Behavior to establish | Test first / verification | Dependency and risk |
|---|---|---|---|---|
| 0.1 | `docs/planning/archive/`, revision record | Preserve originals before replacement | Compare original and archived bytes and SHA-256 for every input | None; never normalize archived line endings |
| 0.2 | Proposed project configuration, local provisioning manifest | Select Python 3.11 interpreter and isolated dependency groups | Offline import test fails clearly for a missing required package; optional engines do not block native imports | 0.1; avoid bare pip because host pip and python may differ |
| 0.3 | Proposed profile/dataset specifications | Define ownership, raw/derived boundary and artifact versions | Table-driven contract tests for consent, relative paths, hashes and incompatible versions | 0.1; schema changes need owner sign-off |
| 0.4 | Proposed test configuration and evidence ledger | Separate native, model-dependent and service suites | Test discovery alone makes no network requests or weight downloads | 0.2 and 0.3; skipped integrations are not successful integrations |

Each row is a deliverable, not a single large patch. Break implementation into test-first changes around 100 lines where practical; split changes over roughly 300 lines. The parent owns implementation coordination and commits. This documentation revision must not edit deployment configuration or application code.

## Contract decisions

- Native baseline: Windows, Python 3.11, CPU. Invoke installation through the selected interpreter, not the host's ambiguous `pip` executable.
- Data roots are configurable local directories. Raw takes are immutable unless the owner explicitly requests deletion. Re-recording appends a take; it never overwrites the previous raw file.
- Profiles use explicit schema version, unique ID, creation time, owner/consent references, permitted uses, language, one primary reference, style references, hashes and relative internal paths.
- Model artifacts have their own version and task kind. The acoustic autoencoder checkpoint must not be mislabeled as a TTS profile or loaded as an OpenVoice speaker representation.
- Tests must be executable offline after provisioning. Native suite must not require Docker, a microphone, speakers, CUDA, pretrained weights or a hosted endpoint.
- Loopback services are optional adapters. Reject remote destinations and redirects; do not infer safety solely from a URL looking local.

## Acceptance criteria

- [ ] All ten original plan files are archived unchanged. The conversation is preserved unchanged and separately copied for historical context. Manifest records all eleven names, byte counts and hashes.
- [ ] The implementer records the actual interpreter, package lock/provisioning policy, free dependency licenses, free disk and RAM, and CPU test command.
- [ ] No credentials, cloud resources, public exposure or data uploads are needed for the native path.
- [ ] Required and optional dependencies are distinguishable. Docker unavailability and missing weights are explicit blockers only for their respective suites.
- [ ] Profile, dataset split, metrics and consent contracts have written tests specified before implementation.

## Open decisions and stop conditions

Owner approval is required before recording a person, provisioning weights, accepting model/data licenses, deleting originals, changing schemas, or modifying deployment/CI configuration. Recommend a single-user loopback product and local files for the first release. Public hosting is not an alternative in this plan.

RAM and free disk are not verified by this document. GPU/container compatibility and model licenses require a bounded feasibility check. If a dependency cannot be made free and offline, exclude it or report the feature blocked. Do not replace it with a paid API.

Proceed to [Phase 1](phase-1.md). Detailed sequencing and uncertainty are in [sequencing](docs/planning/sequencing.md).
