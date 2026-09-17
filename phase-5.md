# Phase 5: real reference-based speech and local clients

**Status: planned, model-dependent.** Implementation specification after [Phase 1](phase-1.md) profiles and [Phase 3](phase-3.md) service contracts. Start a bounded provisioning/compatibility investigation early; do not hold the native ML baseline hostage to it.

## Outcome

Synthesize new text as actual intelligible speech from an authorized reference using locally provisioned OpenVoice V2 and compatible base TTS. Connect a local text-producing assistant through a reusable client. This phase does not fine-tune OpenVoice and does not consume the autoencoder checkpoint as a voice-cloning model.

## Provisioning gate

Before implementation, inspect the pinned upstream OpenVoice V2 workflow and record source revision, converter configuration/checkpoint, base TTS implementation/weights, source speaker representation, tokenizers, language data and every required license. Validate checksums and local paths. No guessed package names, fictional CLI commands or runtime downloads from archived examples.

Use a separate environment if upstream dependencies conflict with native Python 3.11. Prefer a supported local Linux/WSL environment for incompatible native packages. CPU support and GPU fit must be measured for the pinned workflow. An RTX 3050 with 6 GB VRAM is not proof the full stack fits. Keep one worker and avoid simultaneous ML training/TTS GPU residency.

## Increments

| ID | Proposed files | Behavior change | Test first / verification | Dependency and risk |
|---|---|---|---|---|
| 5.1 | Engine capability contract, provisioning manifest and adapter tests | Report supported languages/style/speed and missing local resources explicitly | Missing or corrupt weight/config fails without network or substitute audio | Profiles; base TTS and converter may have different licenses |
| 5.2 | `src/voicefont/engines/openvoice_v2/`, model integration tests | Execute pinned base TTS -> reference representation -> tone conversion workflow | Real known text generates valid nonempty speech; metadata names actual engine and weight hashes | 5.1 and provisioning; validity alone does not prove intelligibility |
| 5.3 | Synthesis API and bounded worker/queue | Return complete WAV for permitted profile and text | Invalid/revoked profile, unsupported controls, timeout and busy queue fail predictably | 5.2 and Phase 3; no blocking model call in async event loop |
| 5.4 | Local Python/CLI client, client tests | Discover capabilities, synthesize, save or optionally play audio | Unavailable service, malformed response, cancellation and resource cleanup tested | 5.3; playback is optional, saved audio is inspectable |
| 5.5 | Local assistant example and evaluation report | Pass actual local assistant output to speech backend | Text-only example is labeled as such; real assistant demo records selected local model and evidence | 5.4; no cloud LLM endpoints or false echo-as-AI claims |

## Evaluation and failure-mode learning

Use the same held-out evaluation sentences across the good, too-short, noisy and monotone reference experiment retained from the original plan. Use only the owner's voice or explicitly authorized material. Preserve all raw takes and outputs privately. Listen to outputs without labeling the reference condition when practical.

Record intelligibility, perceived resemblance, naturalness and audible artifacts as separate ratings with evaluator and sample count. Treat the owner's self-rating as subjective, not a validated benchmark. Record cold/warm wall time, output duration, real-time factor and peak RAM/VRAM. A checksum difference or valid WAV header does not prove speech quality. Do not assert a subsecond target has been met without measurements.

## Acceptance criteria

- [ ] With networking disabled, the real backend produces intelligible new speech for at least three evaluation sentences from one authorized reference. Preserve actual outputs and listening notes.
- [ ] Evidence records exact source/weight versions, local resources, platform and device. Any missing resource gives an explicit unavailable response, not a fake clone.
- [ ] Client and server preserve requested profile/version and supported settings. Unsupported style, language or speed controls are rejected or explicitly reported as unsupported, never silently promised.
- [ ] Queue bounds, timeouts, concurrent-request isolation and cleanup are exercised. Private input text does not appear in URLs or default logs.
- [ ] A local text-input client works without an LLM. Any claimed AI integration uses a real local model, not an echo function or prerecorded response.
- [ ] Reference comparisons and latency results are reported honestly, including failures. No autoencoder loss is used as speech identity evidence.

## Deferral boundary

If no free, permitted, offline compatible weights can be provisioned, mark synthesis blocked and retain native profiles, calibration and ML. Do not generate a tone to make the endpoint appear successful. Ollama is optional only for a concrete local assistant demonstration, not a dependency of voice synthesis, orchestration or tests.

**Handoff:** the real backend and client support [Phase 6](phase-6.md) multi-style experiments and the optional streaming work in [Phase 8](phase-8.md).
