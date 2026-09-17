# Phase 3: fixed calibration and loopback service

**Status: planned.** Implementation specification for contributors after [Phase 1](phase-1.md). This phase can proceed alongside Phase 2 and does not need a speech model.

## Outcome

A person can open a local browser, grant microphone permission, record a fixed guided session, replay or replace takes, pause and resume after restart, and export a validated profile. The same loopback service later hosts real synthesis. Calibration must remain usable if synthesis is unavailable.

## Increments

| ID | Proposed files | Behavior change | Test first / verification | Dependency and risk |
|---|---|---|---|---|
| 3.1 | Local API/capability module, API tests | Expose health, profile listing and analysis without loading optional models | Missing engine reports unavailable, not false healthy synthesis; non-local origins/hosts rejected | Phase 1; loopback alone does not prevent hostile browser requests |
| 3.2 | Calibration corpus and session modules | Persist prompt/take state and accepted selection | Duplicate submissions are idempotent; restart restores accepted takes; re-record does not double-count | 3.1; use atomic persistence and session-scoped IDs |
| 3.3 | Calibration upload/analysis routes | Store raw capture then validated derived WAV | Malformed/oversized upload rejected; original WebM or WAV bytes preserved; derived filename matches actual codec | 3.2; never rename WebM bytes to WAV |
| 3.4 | Bundled local HTML/CSS/JS | Microphone selection, record/stop, replay, re-record, skip, pause/resume and finalize | Browser denial, device loss, upload failure and reload preserve a recoverable state | 3.3; no CDN, web analytics or runtime asset fetch |
| 3.5 | Profile finalization and coverage tests | Export primary reference and coverage provenance | No acceptable take means no final profile; quality rejection cannot count toward completion | 3.4; loudest or largest file is not automatically best |

## Corpus and measurement contract

Start with a complete, small reviewed corpus, then expand toward the original roughly 70-prompt design. Preserve these categories: natural baseline; comfortable low/mid/high pitch; quiet/normal/projected energy; slow/normal/fast tempo; phonetic coverage; questions, lists and contrastive stress; paired emotional deliveries; narrator/friendly/serious/teacher registers; free conversation and repeat checks. Every released corpus has an exact count, IDs, language, version, text, instructions, intended dimensions and license/provenance.

A 15-25 minute session is a usability hypothesis, not a completion requirement. Permit skipping and stopping without pressure. Whisper and projected delivery are optional. Never require extreme pitch, shouting or strained belting; instruct the user to stop if uncomfortable.

Coverage has separate channels:

- **Intended/text-estimated:** phonemes estimated from prompt text or user-provided transcript; tag source and dictionary/language limitations.
- **Observed acoustic:** duration, level, clipping, voiced pitch estimates and confidence/missing values.
- **User-labeled:** intended style and self-assessment, not automatic emotion recognition.

Prompt completion is not proof a phoneme or emotion was spoken. No speech recognition or forced alignment is required in this phase. If later added, it must be locally provisioned and report uncertainty. Words per minute derived from prompt text is an estimate, not a measured transcript.

## API and storage boundaries

Use explicit JSON request bodies and matching response schemas. Validate profile IDs, session IDs and prompt IDs. Bound request bytes and decoded duration. Bind to loopback, validate Host/Origin, restrict cross-origin requests and protect mutation routes against cross-site requests. Avoid private text/audio in logs. Serve only bundled UI assets, never the raw archive as a static directory.

Raw take IDs are immutable. Acceptance selects a take; replacing that selection recomputes coverage from accepted takes instead of accumulating duplicates. Save state after mutations. Finalization writes a new profile version atomically with references chosen by explicit quality criteria and owner approval.

## Acceptance criteria

- [ ] A local browser completes a real three-prompt recording session, including replay, re-record, skip and finalization. Record browser and microphone used.
- [ ] Pause, process restart and browser reload preserve prompt position, accepted takes and coverage exactly.
- [ ] Browser microphone denial and device disconnect show actionable errors; stopping releases the microphone.
- [ ] WAV and any claimed browser codec are actually decoded locally; original capture hash remains unchanged.
- [ ] Re-recording preserves previous raw takes and does not inflate counts. Rejected audio never silently becomes the primary reference.
- [ ] UI labels intended, measured and unknown coverage separately. A silent fixture cannot satisfy speech-coverage completion.
- [ ] Offline browser/API tests and a separate manual microphone report exist. Synthesis capability is explicitly unavailable until Phase 5 passes.

**Handoff:** accepted-take events feed [Phase 4](phase-4.md); profiles feed [Phase 5](phase-5.md). Keep runtime usage examples in implementation docs only after they have been executed.
