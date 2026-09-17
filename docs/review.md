# Native implementation review

## Resolution after review

The parent reproduced both findings with regression tests: 2 failed and 7 passed before fixes. The CLI now disables Uvicorn access logging and only accepts IPv4 loopback (`127.0.0.1`, with `localhost` normalized to it). Unsupported `::1` fails at startup. Final full suite: **85 passed, 7 warnings**; Ruff clean; wheel rebuilt. The historical review below is retained verbatim. These two findings are resolved; no claim of a second independent approval or dependency CVE clearance is made.

## Review summary

**Verdict: REQUEST CHANGES.** Two concrete issues need correction: the default server logs enrollment metadata, and the advertised IPv6 loopback option cannot serve normal IPv6 Host headers. Neither finding implies a remote compromise in the documented single-user loopback deployment.

Reviewed tests before implementation using `C:/Projects/.github/agents/code-reviewer.agent.md`, `C:/Projects/.github/agents/security-auditor.agent.md`, and the code-review-and-quality and security-and-hardening skills. Scope was the current native core and numeric ML workflow, not completion of planned phases. Source and tests were not edited.

## Ranked findings

### 1. Important / Medium privacy: default access logging copies profile metadata into logs

- **Locations:** `C:/Projects/VoiceFont/src/voicefont/api.py:109-115`; `C:/Projects/VoiceFont/src/voicefont/cli.py:85`; `C:/Projects/VoiceFont/tests/test_api_cli.py:111-117`.
- **Observed behavior:** Enrollment places `voice_id`, display `name`, and consent in the URL query. `serve` calls `uvicorn.run` without changing its default access logging. Inspection of the installed Uvicorn configuration and its request-path formatter confirmed `access_log=True` and that the formatted path includes the complete query string. A synthetic example formatted as `/profiles?voice_id=synthetic&name=Synthetic+Fixture&consent=true`.
- **Impact:** Successful and rejected enrollment attempts can copy a person's display name, identifier, and consent assertion into terminal output or wherever server logs are collected. This creates an additional retention location outside the profile store. This is a local privacy problem, not evidence of cloud transmission. Raw WAV bodies are not shown to be logged.
- **Recommended fix:** Disable default Uvicorn access logging in the provided CLI entry point, or install an explicit redacting access logger that omits query values and sensitive profile path segments. Document equivalent settings for custom ASGI launchers. Do not remove useful non-sensitive error reporting.
- **Regression coverage:** Extend the existing monkeypatched `serve` test to assert the privacy-safe logging configuration. If a custom formatter is used, test that synthetic display names and voice IDs do not appear in enrollment and profile-inspection access output, including rejected requests.

### 2. Important / Low security, functional defect: accepted IPv6 binding rejects legitimate requests

- **Locations:** `C:/Projects/VoiceFont/src/voicefont/cli.py:83-85`; `C:/Projects/VoiceFont/src/voicefont/api.py:36-38`; `C:/Projects/VoiceFont/tests/test_api_cli.py:111-117`.
- **Observed behavior:** The CLI explicitly accepts `--host ::1`, and the application allowlist contains `[::1]`. However, the installed `starlette/middleware/trustedhost.py:40` parses the Host header with `split(":")[0]`, so a bracketed IPv6 host does not match that allowlist entry. An in-process request with `Host: 127.0.0.1:8000` returned 200; the same `/health` request with the normal `Host: [::1]:8000` returned 400.
- **Impact:** The IPv6 option is accepted at startup but fails for normal clients. The default IPv4 path works. This is not an access-control bypass.
- **Recommended fix:** Either remove IPv6 from the advertised accepted bindings until supported, or use a correctly parsed exact-host validation boundary that supports bracketed IPv6 while retaining the existing rejection of unrelated hosts. Do not fix this with a wildcard host allowlist.
- **Regression coverage:** Add accepted-host tests for every supported CLI binding, including optional ports, together with the existing unrelated-host rejection. The current CLI test only checks the default bind argument and rejection of `0.0.0.0`.

## Security and architecture assessment

Trust boundaries considered were raw HTTP WAV uploads and query fields, local CLI configuration, owner-trusted profile files, numeric training inputs and recording groups, inherited tracking/tracing configuration, and ML artifacts. Assets were original recordings, profile/consent metadata, model lineage, and local CPU/memory/storage. STRIDE review focused on permission assertions, file tampering, metadata disclosure, resource limits and unintended external I/O. There is no LLM execution or prompt/tool-output boundary in this implementation, so LLM prompt-injection findings are not applicable.

### What's done well

- Consent must be literal `True` before registry enrollment. Safe IDs, reserved Windows names, bounded audio reads, MIME handling and streamed upload limits have focused tests.
- Original audio is preserved with SHA256 and metadata checks. Duplicate enrollment uses exclusive reservation; concurrent duplicate enrollment has a test. Owner-trusted disk and single-user serving are explicitly documented rather than presented as multi-user authorization.
- CPU work is moved off the async upload handlers. Small-registry full reference verification is disclosed in the README rather than advertised as scalable search.
- Numeric training has finite/dimension/row/iteration bounds, original-recording group separation and train-only scaling. Evaluation compares held-out reconstruction to a train-mean baseline and prevents rejected candidates from reaching registration.
- MLflow clients use explicit local SQLite tracking and registry URIs. Artifact paths are checked, inherited remote store URIs are rejected, and telemetry/tracing opt-ins are disabled before the relevant imports. The graph has an explicit recursion bound and no configured remote model calls.
- Model weights are written as numeric NPZ plus JSON, not executable pickle. Saved metadata includes configuration, metrics, run ID, package versions and a dataset digest.
- README and verification documentation clearly distinguish synthetic numeric training, fixed acoustic search and unavailable synthesis. `/speak` explicitly returns 503. No speaker-identification, voice-quality, TTS, optimizer-convergence or full-phase-completion claim is justified by the synthetic tests, and current documentation does not make those claims.

### Lineage and local-only limits, not new blockers

`src/voicefont/pipeline.py:71-76` records a digest of canonicalized feature bytes and recording IDs. `src/voicefont/pipeline.py:100-109` persists that digest with run/package/configuration metadata, but does not preserve split membership, an immutable dataset manifest, checkpoint reload parity, or a source-code revision. These are explicitly remaining work in `README.md:56` and `docs/verification.md:38-39`, not completed capabilities. The present evidence supports a seeded numerical smoke run, not a fully replayable speech experiment. Keep that distinction until the planned lineage and reload gates are exercised.

The local-only design controls the application's configured services, not arbitrary owner-selected network-mounted storage, preconfigured third-party process state, or OS-wide egress. `docs/verification.md:18-32` appropriately describes the parent's Python socket-guarded run and its scope. I did not independently repeat that ML execution or establish host-wide network isolation. No external runtime or paid service was used for this review.

## Verification story

- Read all five current test modules plus fixtures; audio, registry, API, CLI, training, tracking and pipeline source; the demo script, dependency manifest, current README, relevant plans and parent verification record.
- Ran `.venv/Scripts/python.exe -m pytest tests/test_api_cli.py -q -p no:cacheprovider`: **7 passed, 1 upstream AnyIO deprecation warning in 2.10 seconds**. There is no failing existing API test requiring exception-handler repair.
- Used bounded in-process diagnostics for the logging configuration and IPv4/IPv6 Host behavior. No listening server or external connection was needed. An initial IPv6 `TestClient` base URL encountered an upstream test-transport parsing error; supplying the Host header on its normal in-process URL isolated the application result reported above.
- Parent documentation reports **83 tests passed**, lint passed and a wheel built. Those full checks were not rerun unchanged, and are attributed to the parent rather than independently claimed.
- Inspected the installed versions used for the numeric path: NumPy 2.4.6, scikit-learn 1.9.1, LangGraph 1.2.11 and MLflow 3.16.1. A current advisory-database audit was not performed, so this review does not certify dependency CVE clearance.
- No source changes, commits, installations, real voice recordings, synthesis execution or unrelated project inspection. Only `docs/review.md` was created by this reviewer.
