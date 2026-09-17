# React frontend migration

**Reference:** implementation boundaries and observed verification for the local React frontend.

The active UI is now React 19, built by Vite from `frontend/src`. FastAPI no longer serves the imperative `calibration_assets/app.js` application. Existing backend endpoints, corpus snapshots and private recordings remain compatible. The old assets remain as historical source for now; they are not the active UI.

Components cover calibration, recording/replay/import/retakes, saved sessions, profiles, speech jobs and local acoustic experiments. Recorder and WAV validation code were adapted into imported modules. No React CDN, cloud services or Node production server is used.

## Observed verification

- `npm --prefix frontend run build`: passed, 29 transformed modules; no build warnings.
- `npm --prefix frontend test`: four recording-attribution/URL unit tests passed.
- `uv run --offline pytest tests scripts/setup_openvoice_test.py -q`: 197 passed, six opt-in skips, nine non-failing dependency/training warnings.
- `uv run --offline python scripts/browser_e2e.py`: five passed against the actual React production bundle. Generated microphone PCM capture, replay, save, retakes, select, skip, resume, ZIP export, partial profile finalization, library, speech error/cancel UI boundaries and three viewport widths verified. The test server was stopped.
- Latest browser evidence: `data/browser-e2e/20260917-211212/`.
- Ruff passed. Wheel built and contains `voicefont/web/index.html` plus hashed JS/CSS.
- Headless launcher readiness/shutdown passed on port 8031, reporting local-only and synthesis available.
- npm production dependency audit reported zero known advisories. This does not audit Python or establish that all dependencies are trustworthy.

The speech engine was independently exercised before the frontend migration using the durable local Python environment: genuine 3.413333-second, 22050 Hz mono output with Python networking blocked. SHA256: `31deaac0f90a71476002df1ddd99b147aff94dd3548dd2ec04a82b9894c3ae02`. Browser speech failure/cancel tests use explicit network-boundary stubs and are not evidence of neural synthesis. No human listening or speaker similarity evaluation was performed.

## Subsequent regression evidence

A later full browser run (`data/browser-e2e/20260917-211748/`) failed when
`POST /calibration/sessions/{id}/select` returned 503. The saved trace confirms
a backend storage failure, not a JavaScript exception; the underlying OSError
was not recorded, so its root cause remains unknown. Three isolated wizard
runs subsequently passed, including `20260917-212212`, but no fix was made.
Do not treat these passes as resolution of the intermittent failure.
Independent migration review remains incomplete.

## Known remaining work

This migration does not complete optional infrastructure, multi-style TTS, consent deletion/revocation, or a fresh-machine model asset downloader. React interaction race/error recovery needs broader component-level regression coverage and independent review; four utility tests and the happy-path browser suite are not exhaustive. The dedicated React experiment acceptance test now passes: eight generated WAVs, explicit training consent, actual local training, displayed metrics checked against the backend, disjoint train/holdout groups and result restoration after reload. Evidence: `data/browser-e2e/20260917-212052/`.
