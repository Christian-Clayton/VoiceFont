# Local product completion contract

This work delivers the personal local recording -> profile -> speech product. Optional infrastructure demonstrations (Weaviate, Triton, Kubernetes, Terraform) remain separate roadmap work, not prerequisites or claims of this product release. No paid/cloud runtime or hosted tests. Provision dependencies explicitly, then runtime offline.

## Shared API contract for this implementation

Existing `create_app(root)` uses root as profile registry. Sessions live at `root.parent / 'calibration'`. Test roots are disposable. JSON mutations use same-origin checks; no arbitrary origins, no wildcard CORS. Browser page at `/calibrate`, bundled assets `/calibration-assets/`, corpus `/calibration/corpus`. Root `/` can redirect to `/calibrate`.

Corpus JSON: `{version, language, title, disclaimer, categories:[{id,title,description}], prompts:[{id,category,text,instruction,dimensions:[str],optional:bool,style:str}]}`. At least 70 original prompts, en-GB default; accent-neutral delivery: speak naturally, don't imitate. No claim exhaustive phoneme or emotion detection.

Sessions:
- `POST /calibration/sessions` JSON `{name, consent:true, mode:'full'|'adaptive'}` -> session.
- `GET /calibration/sessions` -> session array (metadata, no raw audio).
- `GET /calibration/sessions/{id}` -> session.
- `POST /calibration/sessions/{id}/takes?prompt_id=...&take_id=...` raw PCM WAV -> session. Client generates unique take_id. Repeated identical ID/bytes idempotent; conflict rejected. AudioData supports .1-180s PCM; browser should directly encode WAV from WebAudio rather than renaming MediaRecorder WebM. A take stores quality and raw reference. Reject clipping/silence with actionable error; retain old accepted takes on rerecord.
- `POST /calibration/sessions/{id}/select` JSON `{prompt_id,take_id}` -> session.
- `POST /calibration/sessions/{id}/skip` JSON `{prompt_id}` -> session.
- `GET /calibration/sessions/{id}/takes/{take_id}/audio` -> WAV, exact IDs only.
- `POST /calibration/sessions/{id}/finalize` JSON `{voice_id, name}` -> profile metadata. Explicit primary best neutral reference, preserve whole session. Partial completion allowed with at least 3 distinct accepted prompts across 2 categories; label partial, no fake full coverage.
- `GET /calibration/sessions/{id}/export` -> safe ZIP backup containing session JSON, corpus and all own raw takes. Never include paths outside session.

Session JSON `{id,name,created_at,updated_at,consent,mode,corpus_version,accepted:{prompt_id:take_id},skipped:[prompt_id],takes:[{id,prompt_id,duration_seconds,sha256,quality:{rms,peak,clipping_fraction},style}],coverage:{completed,total,by_category:{category:{completed,total}},label},next_prompt_id,status:'active'|'finalized',profile_id?}`. Adaptive next prompt prioritizes categories with fewer accepted prompts; fixed mode corpus order. No automatic early complete unless actual declared mandatory prompt completion. List/full response excludes local filesystem paths. Rerecord only changes selected take on successful upload.

Speech:
- `GET /synthesis/capabilities` -> `{available,backend,device,message}`.
- `POST /synthesis/jobs` JSON `{voice_id,text,style:'neutral',speed:1.0}` -> `{id,status:'queued'|'running'|'completed'|'failed'|'cancelled',error?,audio_url?}`. Validate text max1000, speed0.75-1.5; one worker, bounded queue, timeout. Backend uses separate provisioned Python3.10 env for OpenVoice, no runtime downloads, local asset config not guessed.
- `GET /synthesis/jobs/{id}` -> job status.
- `POST /synthesis/jobs/{id}/cancel` -> status; kill child if running; no continuing compute after cancellation.
- `GET /synthesis/jobs/{id}/audio` -> real WAV only when completed.
- Existing POST `/speak` may remain compatibility endpoint but must no longer unconditionally503 if backend available; integrate via job flow or bounded synchronous response.

UI primary workflow: consent/start or resume -> current prompt/instructions/category -> record/stop/replay/save/re-record/skip -> coverage and checklist -> finalize -> voice library -> text synthesis/job state/audio/download. Recorder releases microphone on stop/cancel/navigation, max180s capture, catches permissions and device loss, preserves unsaved take until save succeeds. Mobile and keyboard usable. No CDN/fonts/analytics. Export and continue after browser reload.

## Completion evidence

Tests fail first for new behavior; each module focused tests then full suite. Real local browser test with synthetic injected microphone tests mechanics only, no human voice-quality claim. Actual speech synthesis from official technical fixture offline; user's own microphone and listening assessment remain user acceptance, not fabricated by tests. Quality: preserve raw bytes, reject malformed/oversized/unsafe IDs, explicit consent, resume, rerecord, conflict, incomplete finalization, cancellation, unavailable backend. Audit current dependencies and disclose unresolved issues.
