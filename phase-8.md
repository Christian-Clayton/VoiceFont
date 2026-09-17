# Phase 8: optional streaming and evidence-based release

**Status: planned.** Implementation specification and release gate for contributors/reviewers. Native release requires Phases 1 and 2; calibration release adds Phases 3 and 4; speech release adds Phases 5 and 6. Infrastructure showcase claims require Phase 7 independently. Do not require every optional track to release a truthful native milestone.

## Outcome

Make the supported local paths reproducible and inspectable, and add sentence-level streaming only if measured latency warrants it. Documentation must describe executed behavior, not reproduce the original plan's unchecked implementation snippets and prewritten completion claims.

## Increments

| ID | Proposed files | Behavior change | Test first / verification | Dependency and risk |
|---|---|---|---|---|
| 8.1 | Sentence segmentation and bounded playback queue | Overlap real sentence synthesis and playback | Abbreviations, decimals, trailing fragments and long text preserve content/order | Phase 5; no Phase 7 requirement |
| 8.2 | Versioned stream protocol, server/client cancellation | Deliver framed audio incrementally and stop playback/work within declared limits | Arbitrary network fragmentation, malformed frames, disconnect and backpressure tested | 8.1; transport chunks are not complete WAV files |
| 8.3 | Latency comparison report | Compare first audible audio and completion for matched requests | Timestamp when playable audio actually arrives/is submitted to device, not headers or end-of-list iteration | 8.2; cache/warm-up can bias comparisons |
| 8.4 | Environment checks, backup/restore and withdrawal workflows | Verify per-capability readiness without network side effects | Missing optional dependency reports unavailable; restore matches hashes; withdrawal blocks caches/indexes/models in use | Selected release tracks; deletion needs owner approval |
| 8.5 | Runtime README, architecture/profile/API guides, examples and license inventory | Publish only supported, executed local workflows | Each documented command replayed in selected offline environment; links and capability labels checked | 8.4; proposed paths in plans are not source truth |
| 8.6 | Release evidence and reviewer checklist | Package a reproducible milestone with explicit limitations | Clean offline replay, privacy audit and five-axis review have recorded outcomes | 8.5; parent owns commits and release decisions |

## Streaming truthfulness

Keep complete-WAV synthesis as the reliable default. OpenVoice may require complete input per utterance; sentence synthesis can overlap playback of earlier sentences without claiming native token-level audio generation. Dividing an already generated file into HTTP chunks does not reduce generation time. Early response headers are not first audible audio.

Recommend one local WebSocket stream contract with an initial format/version message, ordered length-bounded PCM frames, sequence numbers, end/error messages and a cancellation message. Confirm sample rate, sample width and channel count before playback. A simpler complete-WAV-per-sentence client is a valid first increment, but label its granularity. Do not parse arbitrary HTTP byte chunks as standalone WAV files or concatenate WAV headers into PCM.

Bound queue bytes/duration. On cancellation, stop playback, drop pending frames and cancel future sentence jobs. If the underlying model cannot interrupt an active utterance, report that limit and do not claim GPU computation stopped immediately. Explicit style remains stable across all sentences unless the user requests per-sentence selection.

Benchmark matched cold/warm requests with cache state disclosed. Report first playable audio, first device submission (or measured audible onset where available), total synthesis time, end-to-end duration, real-time factor, gaps/underruns and cancellation delay. Publish median and tail latency with sample count. No guaranteed subsecond claim.

## Release evidence and privacy

Use a capability matrix with planned, implemented-unverified, verified-on-platform, blocked and deferred statuses. Attach actual test commands, environment, exit status, run IDs and artifact hashes. An optional skipped test never verifies its service. Generated fixtures are labeled; no made-up outputs or placeholder AI are shown as ML demonstrations.

Backup/restore covers raw takes, profiles, dataset manifests, local run tracking and selected checkpoints. Consent withdrawal blocks future use immediately, invalidates retrieval/synthesis caches, and quarantines affected trained artifacts until removed or retrained without the withdrawn data. Explain that deleting a row does not erase learned influence from a checkpoint. Any deletion of raw audio or backup copies requires explicit owner confirmation and a documented retention decision.

Review documentation for accidental personal speech, identifying metadata, filesystem paths, private transcripts, credentials and raw audio in repository history. Runtime Swagger/UI assets must be bundled or disabled for offline operation. Keep license decisions separate for code, model weights, datasets, voices and redistributed artifacts.

## Acceptance criteria

- [ ] Selected release tracks replay offline from explicitly provisioned dependencies. Native CPU remains usable with services and speech weights absent.
- [ ] Optional streaming plays real first-sentence audio before later sentence synthesis completes, or the feature is honestly deferred. Frame fragmentation, order, final fragment, backpressure and cancellation tests pass.
- [ ] Performance report measures playable audio rather than headers and states platform, backend, sample count, cache state and limitations.
- [ ] Local backup/restore reproduces profile/reference/model hashes. Withdrawal blocks stale search and synthesis paths and marks affected training artifacts unusable.
- [ ] Runtime documentation commands and examples are executed, licenses recorded, links checked and every limitation visible. These plan files remain explicitly future-facing.
- [ ] Independent reviewer checks correctness, readability, architecture, security and performance. No source-control action or public release is automatic.

## Definition of completion

A native ML milestone can be complete while synthesis, streaming or Kubernetes is blocked. The full voice product is complete only with real speech, calibration, multi-style evidence, portability and privacy gates. The optional MLOps showcase is complete only after real service execution. Never collapse these three claims into one checked box.

Return to [PROJECT.md](PROJECT.md) for scope and [validation](docs/planning/validation.md) for the evidence format.
