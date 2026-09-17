# Refinement gap analysis: voice capture, tone-aware TTS, employability

**Explanation + roadmap, grounded in what is actually built.** Each section
separates shipped work (commit-verified) from genuine gaps. No coverage
percentages and no claims of "capturing every aspect" - that is not achievable
by any finite pipeline, and pretending otherwise would be the biggest
credibility risk in a senior AI/ML interview.

## 1. Voice capture completeness

Shipped (verified by tests):

- 75-prompt calibration corpus (7 categories, 54 core) spanning phonetic
  coverage, connected speech, questions, emphasis pairs, pitch/volume/range,
  pausing and unscripted consistency repeats.
- `voicefont.prosody` (`prosody-v1`): deterministic per-frame F0 (autocorrelation
  with parabolic refinement), RMS energy, spectral centroid; relative voicing
  masking; bounded summary (pitch min/median/max, energy min/max, energy trend,
  voiced fraction).
- Every enrolled profile now stores a `prosody.json` sidecar computed from the
  selected reference at finalize; readable via `ProfileStore.get_prosody`
  without touching raw audio; legacy profiles read as `None`.

Honest gaps (the real "capture every aspect" ceiling):

- We measure pitch/energy/brightness, not articulation (formants, VOT), voice
  quality (jitter, shimmer, HNR), or prosodic *meaning* (contrastive stress,
  irony). These need targeted DSP work or a pretrained speech model - the
  natural next milestones, each independently testable.
- The OpenVoice pipeline does reference-based tone conversion: it transfers a
  global timbre, not these measured contours. Matching your actual pitch
  dynamics requires either controllable TTS (prosody-conditioned) or a
  fine-tuned model - both out of scope of the current MIT-licensed stack and
  explicitly not claimed.
- Human acceptance is missing by design: only you can judge whether a synthesized
  voice sounds like you. The wizard is built for exactly this - record, enroll,
  synthesize, listen.

## 2. Tone-aware TTS

Shipped (verified by tests):

- `voicefont.tone` (`tone-v1`): deterministic lexicon/punctuation analysis
  producing valence, arousal, urgency, question and exclamation counts.
- Every speech job analyzes its text at submission; completed jobs report the
  `tone` block next to `audio_url`. Failed jobs keep the minimal generic
  contract (no derived text data on failures).
- `POST /synthesis/tone` returns analysis without synthesizing, so a client can
  preview delivery before spending synthesis time.

Honest gaps:

- The analyzer informs delivery; it does not yet steer it. The engine's only
  controls are neutral style and speed (0.75-1.5). The intended wiring -
  urgency/arousal mapping to speed and pause structure - is the next increment
  and is deliberately exposed as analysis first so the decision point is
  inspectable rather than hidden inside the worker.
- Lexicon analysis is transparent but shallow; it cannot detect sarcasm,
  sentiment composition or domain-specific tone. A small local transformer
  classifier (fine-tuned, still offline) would be the credible upgrade path.

## 3. Employability surface (senior AI/ML signal)

What this repo already demonstrates to an employer, with evidence:

- **ML:** real scikit-learn training with heldout gates, seeded reproducibility,
  LangGraph state machine, local MLflow tracking with run lineage, published
  vs rejected model gates.
- **ML engineering:** bounded subprocess isolation, queue bounds, cancellation
  that kills process trees, cleanup-fault degradation (fail closed), schema
  versioning with fail-closed reads, integrity-hash verification before
  deserializing checkpoints.
- **Backend/API:** FastAPI, same-origin policy, bounded JSON bodies, job
  contract evolution without breaking old clients.
- **Product engineering:** React 19 migration with Vite, WebAudio PCM capture,
  durable resumable sessions, Playwright E2E, double-click launcher with
  pre-flight checks.
- **Verification discipline:** ~220 focused tests, RED/GREEN evidence, honest
  unavailable-capability states, no fabricated speech quality claims.

Highest-value additions for senior-signal (ordered by leverage):

1. **Prosody-controllable synthesis demo** - even a speed/pause mapping driven
   by tone analysis converts "we measured" into "we closed the loop".
2. **Evaluation harness with numbers** - intelligibility/similarity metrics on
   generated audio (even self-reported MOS-style listening forms), charts in the
   README. Senior interviews ask "how did you evaluate?"
3. **Packaged reproducibility** - the ~831 MB runtime bundle is a known gap for
   fresh machines; a documented manifest-based downloader (opt-in, hash-verified)
   would show release engineering maturity.
4. **CI workflow** - the suite is fully local and fast; a GitHub Actions gate
   makes the discipline visible without any hosted testing of the product.
5. **Consent lifecycle** - revocation and deletion workflows are documented as
   missing; implementing them would demonstrate GDPR-grade data thinking.

## 4. What we deliberately did not do

- No cloud APIs, hosted tests, telemetry or CDN assets.
- No claims that acoustic similarity, prosody statistics or tone analysis
  constitute speaker identification or emotion recognition of a person.
- No silent fallbacks: missing runtime = explicit unavailable capability.
