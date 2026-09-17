# Phase 1: native audio and portable profiles

**Status: planned.** Implementation specification for a contributor starting from [Phase 0](phase-0.md). Nothing here claims an existing command or feature works.

## Outcome

An owner can inspect a local WAV, receive a signal-quality report, and build a portable profile without Docker, pretrained models or a network connection. This delivers ownership and validation before the ML experiment in [Phase 2](phase-2.md).

## Increments

| ID | Proposed files | User-visible change | Failing test to write first | Depends on / risk |
|---|---|---|---|---|
| 1.1 | `src/voicefont/audio.py`, `tests/test_audio.py` | Inspect supported PCM WAV and report duration, sample rate, channels, peak, RMS and clipping fraction | Empty, truncated, unsupported, non-finite and oversized input are rejected without partial output | Phase 0; malformed audio can exhaust resources |
| 1.2 | `src/voicefont/profiles.py`, `tests/test_profiles.py` | Build and load an inspectable versioned profile | Missing consent, invalid ID, hash mismatch and escaping reference path fail | 1.1; validate containment including Windows paths and links |
| 1.3 | `src/voicefont/cli.py`, `tests/test_cli.py` | Perform analysis and profile round-trip through a native CLI | Invalid input yields nonzero exit status and useful error; valid input yields machine-readable output | 1.2; CLI must not silently mutate input |
| 1.4 | Profile export/import boundary, portability tests | Move a bundle to another directory and rebuild derivatives | Relocated profile resolves all internal references; unsupported major version fails | 1.3; do not rely on original absolute paths |

Paths are proposed responsibilities, not instructions to copy archived code. Adapt names to the actual source layout while preserving these testable boundaries. Run the selected environment's `python -m pytest` after each increment; that is a planned verification command, not execution evidence from this document.

## Input and artifact rules

Start with a deliberately narrow supported WAV format. Reject unsupported codecs explicitly before broadening format support. Bound file bytes, decoded duration and frame count independently. Measure clipping on decoded original samples before normalization. Label RMS and peak units, silence thresholds and channel reduction policy.

Retain the raw source as an immutable copy with its content hash. Normalize or resample only derived files with source hash, sample-rate conversion method and preprocessing version. Preserve original channel count and sample rate metadata.

A portable profile bundles reference files, not links to arbitrary external locations. An optional archive pointer is provenance, not required to load the profile after relocation. Keep engine-specific caches in a separate namespace keyed by engine/version and reference hash.

Consent fields include who authorized use, scope, recorded time and withdrawal status. Enrollment must require explicit affirmative consent. The system does not prove legal identity from a checkbox. Generated audio must be labeled as generated in metadata and user-facing demos.

## Acceptance criteria

- [ ] Valid mono and explicitly supported multichannel WAV fixtures yield finite documented metrics. Silence and clipping are flagged, not described as identity or clone-quality scores.
- [ ] All invalid-input cases return controlled errors. No output is left half-written and no raw file is changed.
- [ ] A profile can be created, validated, exported, moved and reloaded with identical reference hashes.
- [ ] Exactly one primary reference exists. Invalid IDs, duplicate styles, missing references, absolute/parent-traversing paths and incompatible major schemas fail validation.
- [ ] Consent denial or withdrawal prevents enrollment/use and does not trigger a network call.
- [ ] Native CLI and tests complete with network unavailable, no microphone permission request and no optional-service imports.

## Learning experiment and limits

Preserve the original good/short/noisy/monotone comparison idea as an authorized recording experiment. In this phase compare input quality only. Later, Phase 5 can synthesize the same text from those references and record actual outcomes. Do not assume every deliberately worse input creates a worse clone.

Signal fixtures may test numerical edge cases. A sine wave proves WAV processing only, not speech, cloning or a trained model. Keep personal recordings and profiles out of source control. Backup is a local user-controlled copy, not a commit.

**Exit handoff:** validated profile/data boundaries for Phases 2 and 3. Failure of real synthesis feasibility does not invalidate this native deliverable.
