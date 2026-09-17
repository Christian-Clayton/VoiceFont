# Local acoustic ML experiments

## Run from the workspace

Open **Acoustic ML** in the `/calibrate` navigation, expand the optional panel, and choose a saved calibration session. The independent panel does not replace the recording wizard. The navigation stops an active capture via the existing Stop control; unsaved takes stay in the wizard and are not used for training.

Record and select at least **8 distinct original WAVs** first. Earlier unselected takes are excluded, and byte-identical WAVs count once even when saved under different prompts. Partial and finalized sessions are eligible. Session consent alone is not training consent: check the separate authorisation box, then choose **Train local acoustic model**. Changing the session clears that checkbox. There is no automatic training, upload, download or cloud service.

The panel shows queued/running status and the actual completed heldout MSE, training-mean baseline MSE, gate pass/rejection, graph stages and local MLflow run ID. It remembers the last experiment ID in browser local storage; reopening the panel after reload retrieves the durable server result. Network failures expose **Check status**, not an automatic second training request.

## What is trained

Each selected, integrity-verified PCM WAV goes through the existing `read_audio` and `extract_features` functions. One `acoustic-v1` vector has 16 descriptors: spectral band energy, RMS, zero crossings, spectral centroid and spread. No synthetic features or placeholder metrics are substituted if reading, extraction or ML fails.

The existing `run_pipeline` executes a compiled LangGraph:

`preprocess → train → evaluate → publish only if the gate passes`

Original WAV SHA256 hashes are the recording groups. Duplicate hashes are deduplicated before the split. `GroupShuffleSplit` uses seed 7 and a 25% heldout fraction. The scaler is fitted on training recordings only. No windows, repeated takes of the same bytes, or augmented rows cross between training and holdout. Different encodings of the same sound are not detected as duplicates; this is byte provenance, not an audio similarity detector.

The model is the existing scikit-learn tanh MLP reconstruction autoencoder (2-unit bottleneck, maximum 250 iterations). The baseline predicts the training-set mean, represented by zero after train-only standardisation. Gate acceptance requires finite heldout MSE ≤ 0.5 **and** ≤ half the baseline MSE. Rejection is an honest experimental outcome: metrics remain, no numeric model is published. Optimisation may reach its iteration limit without convergence, especially on small datasets; a completed run does not imply convergence.

**This is not TTS, voice cloning, speaker identity training or a speech-quality assessment.** There is no text conditioning. Passing publishes numeric weights in the local MLflow registry, not a speech voice. The experiment never modifies speech profiles. A tiny within-session holdout cannot establish cross-session, microphone or speaker generalisation. Repeated experiments use the same split and must not be presented as independent test evidence.

## Bounds and persistence

- One non-queued background worker per application process; an OS file lock additionally prevents two processes training against the same experiment root. Concurrent creation returns 409.
- 8–100 distinct recordings, no more than 1,800 seconds or 128 MiB of selected raw audio per run; at most 100 stored experiments. No automatic deletion.
- Input bytes and duration, feature dimensions, graph recursion and training iterations are bounded. This is a background thread, not a hard wall-clock-isolated process; there is no cancellation endpoint. Close the application to interrupt it.
- Snapshot selection happens on explicit start. Subsequent selection changes do not add data to an in-flight run. Each snapshotted original is loaded through `CalibrationStore.audio`, which verifies identity, safe paths, file links and byte hashes.
- Results live at `profile_root.parent/experiments/<id>/result.json`, with run-specific `mlflow.db` and filesystem `artifacts/`. Result JSON is size-limited and atomically replaced; reads/writes share a mutex to avoid Windows open-file replacement races. Model artifacts use numeric NPZ and JSON, not pickle.
- Raw audio remains in calibration storage. The public result contains no local paths. Private exception traces remain local server diagnostics, not HTTP fields. Protect the data directory with owner filesystem permissions; this is a trusted-disk single-user local application, not a hosted multi-tenant service.
- On application restart, interrupted queued/running results are marked failed, never silently resumed. Start a new explicitly consented run. Back up the experiments directory while the app is stopped to retain metrics and accepted models.

## Integration API

Mount `create_experiment_router(profile_root)` from `voicefont.experiment_routes` in the existing loopback-only FastAPI application. No additional lifespan hook is required.

- `GET /experiments/capabilities`: optional ML dependency availability, bounds and limitations. Missing dependencies require an explicit install of the project's `ml` extra; nothing installs at runtime.
- `POST /experiments` with JSON `{"session_id":"<saved-session-id>","consent":true}`: 202 and `{id,session_id,status,consent,created_at,...}`. Consent must be the literal boolean `true`; extra fields are forbidden. Insufficient data returns 422 before any job or MLflow run is created.
- `GET /experiments/{id}`: persistent status/result. Completed reports include `report.metrics.validation_mse`, `report.metrics.baseline_mse`, `gate_passed`, `report.stages`, `report.run_id` and the disjoint original hash groups in `dataset`.

Routes reuse same-origin checks and bounded JSON parsing from calibration routes. Unknown IDs return 404; malformed IDs return 422; cross-origin access returns 403; storage unavailability returns 503. There is no arbitrary data-path, model-path, URL, configuration or feature-matrix input.

## Verification

`tests/test_experiment.py` uses isolated temporary calibration stores populated only by clearly labelled **generated multitone/noise PCM signals**, not user recordings. These tests prove mechanics, not voice-model quality. Real jobs exercise feature extraction, LangGraph, sklearn, SQLite MLflow and durable API results. Other tests cover explicit consent, minimum distinct hashes, unselected take exclusion, duplicate deduplication, one-job admission, safe failure, corrupt audio, restart recovery and unsafe result paths/hardlinks.

Run with the installed project environment:

```text
.venv/Scripts/python.exe -m pytest tests/test_experiment.py tests/test_pipeline.py tests/test_training.py -q
.venv/Scripts/python.exe -m ruff check src/voicefont/experiment.py src/voicefont/experiment_routes.py tests/test_experiment.py
node --check src/voicefont/calibration_assets/experiments.js
```

Browser integration and the actual user's authorised recordings/listening assessment remain separate acceptance checks. No user recordings are accessed by this test suite.
