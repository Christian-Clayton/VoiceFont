# Independent local-product review

**Verdict: REQUEST CHANGES**

Reviewed the completed calibration, synthesis and core browser implementation against `docs/product-contract.md`, using the code-reviewer and security-auditor agent guidance and the code-review-and-quality/security-and-hardening skills. The ordinary recording-to-profile and bounded job happy paths work in the focused tests, but recovery and lifecycle defects remain. Findings below are static conclusions unless explicitly identified as executed verification; no security exploit or vulnerability reproduction was run.

## Scope and assumptions

- In scope: `src/voicefont/{calibration,calibration_routes,synthesis,synthesis_routes,api,corpus}.py`, `calibration_assets/{app,recorder,wav}.js`, and corresponding tests. Read `audio.py`, `registry.py` and the page markup as dependencies of these paths.
- Excluded: independently owned experiment modules and setup/browser scripts. Browser tests were inspected, not executed. No user's recordings or personal profiles were opened or used.
- Threat model: a single owner, owner-trusted local disk/configuration, an unauthenticated service intentionally bound to loopback, browser requests as a separate input boundary, and a provisioned local subprocess. This is not an authenticated remote service. Host/origin validation is not a replacement for loopback socket binding.
- No external calls, uploads, installations or dependency-advisory queries were performed. No fresh dependency security verdict or independent proof of subprocess network isolation is supplied by this review.
- Working tree was concurrently changing. Line numbers refer to files read during this pass. Only this report was intentionally created by the reviewer; no implementation edits or commits.

## Prioritized actionable findings

### 1. Important / P1 — Cleanup failure can kill the sole speech coordinator and strand later jobs

**Location:** `src/voicefont/synthesis.py:373-390`, especially `383-389`; coordinator startup at `281-285`.

The coordinator assigns a terminal status before deleting temporary reference files. The completed-job cleanup uses throwing `iterdir`, `rmtree` and `unlink` calls inside `finally`, outside the surrounding error handlers. An ordinary filesystem error (including a temporarily locked file on Windows) therefore exits `_work` before `job.done.set()` and before processing any later jobs. `_thread` remains non-null, so subsequent submissions do not create a replacement coordinator. Public state may already say `completed` while `wait()` never observes completion, and queued work remains queued indefinitely.

**Fix:** Make completion signalling unconditional in a nested `finally`; handle cleanup errors separately from generation, with an explicit safe failure/degraded state and a bounded retry or shutdown cleanup policy. Do not silently mark private-reference cleanup successful when it failed. Ensure an unexpected coordinator exit cannot leave the service accepting work it will never run.

**Verification needed:** Ordinary filesystem fault injection during successful-job cleanup must still release waiters and allow the next job to finish (or explicitly reject further submission). Existing success/failure/timeout tests do not cover cleanup exceptions.

### 2. Important / P2 — Resuming a session uses the current corpus instead of its saved corpus

**Location:** `src/voicefont/calibration_assets/app.js:82-112,119-125,381-384`; `src/voicefont/calibration.py:235-257,499-504`; `src/voicefont/calibration_routes.py:112-114`.

The server correctly saves `_corpus` with each session and computes coverage/next prompt against that snapshot. The browser fetches only the globally current `/calibration/corpus`, keeps it in `state.corpus`, and uses it for all resumed sessions. It neither checks `session.corpus_version` nor retrieves the session snapshot. After a corpus update, changed text/instructions for a retained prompt ID can be recorded under the old prompt definition; removed IDs fall back to the current first prompt, and displayed totals/categories can disagree with persisted coverage. This undermines the intended durable correspondence between prompt and audio even though the raw bytes remain intact.

**Fix:** Expose a read-only session corpus endpoint (or include its bounded snapshot in the individual-session response) and load that snapshot before rendering a resumed session. Preserve a separate current corpus for new sessions. At minimum, block recording on version mismatch rather than silently reinterpreting prompts.

**Verification needed:** Browser resume of an old session after changing bundled prompt text, IDs and category counts. `test_snapshot_corpus_and_skip_then_record` verifies the store only, so it does not catch this browser/server mismatch.

### 3. Important / P2 — Finalization can persist an unrecoverable lock before validating its reference

**Location:** `src/voicefont/calibration.py:260-262,418-436`; browser retry fields at `calibration_assets/app.js:346-350`.

Finalization persists `_finalizing` before `_audio` checks the chosen raw reference. If that accepted take has become missing or fails integrity, the finalize call fails but the marker remains. `_active` then prevents uploading/selecting a replacement take, while subsequent finalize attempts recompute the same primary and hit the same failure. The analogous profile-ID collision between the initial existence check and `enroll` also leaves an intent which cannot be changed through the API. The public session hides `_finalizing`, so a resumed browser cannot even discover which exact ID/name must be retried. The existing recovery test covers only failure of the last session metadata save after a profile was successfully created.

**Fix:** Validate/read the selected reference before persisting intent. Design an explicit recovery state: expose non-sensitive intended profile ID/name and permit safe abort/reselection where no matching profile was published. Preserve the recover-forward behavior for the case where a matching profile was already published; do not overwrite an unrelated profile.

**Verification needed:** Functional storage-failure recovery around the pre-enrollment and enrollment stages, in addition to the existing post-enrollment recovery test. Demonstrate that the user can recover through supported API/UI actions without manually editing session JSON.

### 4. Important / P2 — Speech request field limits do not bound HTTP body allocation

**Location:** `src/voicefont/synthesis_routes.py:18-23,67-69`; `src/voicefont/api.py:181-183`. Contrast the bounded streaming parser in `calibration_routes.py:53-79`.

Both speech entry points use FastAPI's automatic `SpeechRequest` body parsing. Their text/field constraints are applied after the request body has been read and JSON parsed. There is no body-byte limit on these routes or a shared application receive limit. The bounded queue therefore limits accepted synthesis work, but not memory consumed before validation. This is a defensive resource-boundary gap, not evidence of a remote compromise; severity is reduced by the loopback-only deployment and foreign-origin protections.

**Fix:** Apply a small streaming JSON byte cap before parsing on both `/speak` and `/synthesis/jobs`, using one shared parser/policy, or enforce an equivalent ASGI receive limit. A Content-Length check alone is insufficient. Keep ordinary strict model validation after that cap.

**Verification needed:** Review/tests of the bounded receive policy on both aliases, including absent Content-Length. No oversized-payload reproduction was performed in this review.

**Security classification:** Medium; availability/resource consumption (OWASP insecure design/security misconfiguration), not a demonstrated confidentiality breach.

### 5. Important / P2 — A failed cancellation can leave the browser permanently waiting

**Location:** `src/voicefont/calibration_assets/app.js:292-304,365-370`; server cancellation timeout at `src/voicefont/synthesis.py:320-323`.

The cancel handler stops automatic polling before issuing the cancellation request. If the request fails or the server legitimately reports that cancellation is still in progress, the generic `run` handler shows an error, but the cancel handler neither restarts polling nor exposes `check-job`. That button is normally hidden by the previous successful status check. `state.job` remains queued/running, so Generate remains disabled even if the server subsequently finishes or cancels the job. Repeated cancellation is not a substitute for restoring status observation, particularly after a transient request failure.

**Fix:** On cancellation failure, retain the job identity, reveal Check job status and resume bounded status polling. Reconcile the eventual terminal state before enabling a new job. Do not report cancellation as complete until the server does.

**Verification needed:** UI cancellation request failure after a successful running-status poll, followed by a terminal status response. Existing browser boundary tests cover failed polling followed by successful cancellation, not this reverse ordering.

### 6. Important / P2 — Resume requests are not serialized with recording or session creation

**Location:** `src/voicefont/calibration_assets/app.js:119-125,134-137`; contrast operation locking at `185-193`.

The Resume handler checks `canLeave()` only before its asynchronous GET. It never sets `state.busy` and never checks whether its result is stale. Multiple resume requests, or Resume followed by starting another session, can therefore be in flight together. An older response can later execute `showSession`, replace `state.session` and choose a different prompt after recording has already begun in the newer session. `captured()` assigns a draft to the then-current prompt, not the prompt/session at capture start. This creates a real recording-attribution race on an otherwise ordinary UI path; the raw recording can be saved against a session/prompt other than the one displayed when the user started reading.

**Fix:** Serialize session transitions with the existing busy state and use a request generation/token to reject stale responses. Bind each capture/draft to immutable session ID and prompt ID at recording start, and verify those bindings before upload. A late session response must not change capture context.

**Verification needed:** Delayed resume response interleaved with a second session transition and recording start. Current resume coverage tests wait for each response before the next action and do not cover this ordering.

## Additional observations, not release-blocking findings

- `synthesis.py:44-65,68-77`: runtime capability checking verifies configured paths and manifest file sizes, not successful model import/execution. The API message says “configured”, which is appropriately limited, but the browser's “Engine ready” label at `app.js:257` is stronger. Prefer “Engine configured” unless backed by a cached successful readiness probe. The configuration parser should also reject non-object JSON explicitly: `.get` on a list/null raises `AttributeError`, outside the current capability fallback exceptions.
- `calibration.py:516-522` and the profile-list dependency fail an entire list when one stored entry is invalid. Consider returning usable entries plus a sanitized per-entry recovery warning, while keeping corrupt entries unusable for enrollment/synthesis. Never silently treat corrupt consent as active.
- `app.js:318` forgets a submission whose response is lost, and page reload forgets job identity. The server may legitimately continue bounded work. Consider a client-generated idempotency key and recoverable local job identity, without storing speech text/audio unnecessarily.
- `wav.js` is a structural UI check, not the final acceptance boundary; the server still performs PCM and signal-quality validation. The recorder captures raw PCM, explicitly caps frames/time, stops tracks and closes the audio context. No remote asset references or user-content HTML interpolation were found in the reviewed core browser code.

## What's done well

- Calibration consent is strict, affirmative and persisted; synthesis checks profile consent and integrity both before accepting a job and again before queued execution.
- Immutable take IDs, byte hashes, atomic metadata replacement, cross-process serialization, rerecord preservation and an allowlisted ZIP export protect the main data path.
- Raw WAV and calibration JSON receive byte caps while streaming. Session/take counts and per-session audio storage are bounded.
- Shared `/speak` and job submission use the same synthesis service. The queue has one coordinator, bounded outstanding jobs and bounded retained results; normal lifespan shutdown closes the service.
- Foreign origins/cross-site requests are rejected, the packaged asset route is allowlisted, and CSP/no-store/nosniff controls are present. Reviewed subprocess arguments are owner-configured, not HTTP-selected; speech text/reference travel over stdin rather than command-line text or logs.
- Coverage is explicitly recording coverage, not measured phoneme accuracy or voice similarity. Neutral-only synthesis and human listening acceptance are disclosed. Generated-signal tests are labelled mechanics-only, and the heavy technical fixture is not presented as a consenting user's voice-quality test.

## Verification story

**Executed locally with disposable generated data:**

```text
.venv/Scripts/python.exe -m pytest -q \
  tests/test_calibration.py::test_routes_complete_contract \
  tests/test_calibration.py::test_concurrent_submissions_do_not_lose_takes \
  tests/test_calibration.py::test_snapshot_corpus_and_skip_then_record \
  tests/test_corpus.py::test_corpus_is_original_bounded_and_complete \
  tests/test_corpus.py::test_load_returns_deep_detached_copy \
  tests/test_corpus.py::test_printable_checklist_exactly_matches_json \
  tests/test_calibration_page.py::test_calibration_page_and_corpus_are_served_locally \
  tests/test_synthesis.py::test_job_contract_and_download

8 passed, 1 warning in 6.55s
```

- Warning: Starlette TestClient uses deprecated `anyio.abc.BlockingPortal`; non-failing dependency warning.
- Independent corpus count: **75 prompts, 75 distinct IDs, 54 core prompts, 7 categories**.
- Ordinary Node PCM encode/validate check: **9,644 bytes, 48,000 Hz, mono, 0.1 seconds**; assertion passed.
- Synthesis happy-path test uses the explicitly labelled `BoundaryBackend` generated signal. It is **not** neural-speech evidence.
- The parent's reported full result (**155 passed, one heavy skip**, lint clean except active child scripts) is context, not an independently rerun result. No full build, full suite, real speech generation, browser run or security probe was performed by this reviewer.

Resolve the six findings above with focused regression coverage, then rerun the integrated product suite. New experiment/setup/browser-script work still needs its own review after its owners finish.
