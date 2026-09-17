# Browser verification (local, generated audio only)

Reproducible Playwright E2E for the bundled `/calibrate` UI. The microphone is
Chromium's fake capture device fed a **generated two-tone PCM fixture** — it is
explicitly **not a human recording and not evidence of speech or voice quality**;
the tests verify recorder/session/export/synthesis *mechanics* only. No cloud
browser, no real microphone, no external requests (all non-loopback aborted).

## Run

```bash
# One-time provision (dev extra, Windows):
uv pip install --python .venv/Scripts/python.exe "playwright==1.63.0"

# Full run: starts its own loopback server on an isolated data root, then stops it
.venv/Scripts/python.exe scripts/browser_e2e.py
# Options: --headed | --browser "C:/path/to/chrome.exe" | --output <new dir>
```

Requires an installed Chrome/Chromium or Edge executable (auto-detected; no
Playwright browser download). `VOICEFONT_OPENVOICE_CONFIG` points at an
intentionally nonexistent path so the unavailable speech path is exercised
without runtime weights; genuine synthesis is verified separately.

## What is covered

| Flow | Evidence |
|---|---|
| Consent gate | unchecked consent blocks submit; `{consent:false}` rejected 422 by server |
| Native WebAudio capture | real `getUserMedia` → `createScriptProcessor` callbacks → PCM encoded by `recorder.js`; track `ended` + `AudioContext.state==='closed'` asserted |
| Stop / replay / save | saved take duration from actual captured frames; POST `/takes` 200 |
| Retake / select | earlier take kept, selection switches, replay from server audio |
| Skip, reload/resume | skipped prompt persisted; reload → Resume restores takes/selection |
| Finalize boundary | below 3-prompts/2-categories rejected 422, session stays active |
| 3 prompts / 2 categories | finalize creates profile, library view + persisted after reload |
| Export ZIP | 4 byte-preserved PCM WAVs (sha256 match, 48 kHz mono 16-bit), safe paths, session+corpus JSON |
| Synthesis boundaries | injected 503 submit and 503 poll via route stubs; cancel; disabled UI with real unavailable engine; no fabricated audio |
| Viewport overflow | 1440×1000, 390×844, 320×740 across setup/studio/finalize/library/speech views |
| Guards | page errors, console errors, ≥400 responses (expected set only), non-loopback abort, WebSocket block |

## Evidence layout

`data/browser-e2e/<timestamp>/`: `run.json` (server lifecycle), `server.log`,
`pytest.log`, `junit.xml`, `GENERATED-NOT-A-VOICE.wav`, `browser.json`,
per-test traces (`trace.zip`), screenshots (`final.png`, viewport `.png`s),
`evidence.json` (console/network/capture checks), exported ZIP, finalized
profile JSON.

## Notes

- Tests live in `tests/e2e/` (skipped by the normal unit suite unless
  `VOICEFONT_E2E=1`; driver: `scripts/browser_e2e.py`).
- Product CSP (`script-src 'self'`, no `unsafe-eval`) forbids `eval`; test
  predicates use arrow-function form, which Playwright compiles safely.
## Recorded execution (17 September 2026)

Evidence root: `data/browser-e2e/20260917-203651/`.
Chrome **152.0.7977.84**, Python **3.11.16**, Playwright **1.63.0**.
Result: **5 test bodies passed, 1 teardown error**, exit 1. The suite deliberately
remains red because it detected an application console error; it is not a clean
pass. `run.json` verifies `server_stopped: true`. There were **0 page errors,
0 non-loopback requests**, and no horizontal overflow in the measured views.
The synthesis network responses are explicitly injected fault fixtures, not
engine outputs or proof of worker-process cancellation. The actual unavailable
capability response uses the real server.

### Reproducible bug: profile ID pattern is invalid in Chromium

Selector: `#voice-id`, source `src/voicefont/calibration_assets/index.html`.

1. Start a generated test session and choose **Create voice profile**.
2. Fill the Profile ID field and submit (or run `checkValidity()` on it).
3. Chrome emits `Pattern attribute value [A-Za-z0-9][A-Za-z0-9_-]{0,63}
   is not a valid regular expression ... /v: Invalid character in character class`.
4. The browser ignores the broken pattern: setting `invalid id!` and calling
   `checkValidity()` returns **true**, recorded under `profile ID client validation`
   in the wizard's `evidence.json`. Server validation still applies.

The unescaped hyphen needs a Unicode-sets-compatible pattern. No application
files were edited. Regression evidence is in the wizard test's `evidence.json`,
`trace.zip`, and the root `junit.xml` / `pytest.log`; the console guard fails.
The current recorder also emits the expected ScriptProcessor deprecation warning,
retained in the console evidence (warnings are recorded, not treated as errors).

### Additional verification

`python -m ruff check scripts/browser_e2e.py tests/e2e`: **all checks passed**.
A concurrent full non-browser run (`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
.venv/Scripts/python.exe -m pytest -q --ignore=tests/e2e`) returned **164 passed,
3 failed, 1 heavy-test skip**. All failures were in the concurrently developed
`tests/test_experiment.py`: real background persistence, failure persistence, and
API real-job completion; logs showed Windows `PermissionError [WinError 5]`
replacing `result.json`, with one job remaining running until the 90-second test
timeout. These are outside this browser task's ownership and must be rerun by
the experiment owner after their changes settle.

The driver disables automatic pytest plugin loading and LangSmith tracing.
Routing guards cover the browser context's HTTP requests and block WebSockets;
this is application-request evidence, not an OS-wide packet-capture claim.
