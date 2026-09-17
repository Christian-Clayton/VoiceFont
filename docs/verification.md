# Native baseline verification

Verified on Windows 11 with Python 3.11.16. This records observed results, not completion of the full roadmap.

## Parent integration checks

- `uv sync --extra ml --extra dev`: completed; dependency lockfile generated.
- `uv run --offline pytest -q`: **83 passed, 7 warnings in 78.53 seconds**.
- `uv run --offline ruff check src tests scripts`: **All checks passed**.
- `uv build --wheel`: built `dist/voicefont-0.1.0-py3-none-any.whl`.
- Archive verification: **11/11 original document hashes match**; root `conversation.md` is unchanged.
- Docker Desktop starts and `docker info` reports server 28.4.0. No VoiceFont container, Kubernetes, Helm or Terraform deployment has been exercised.

Warnings were one upstream AnyIO alias deprecation and six sklearn convergence warnings from deliberately bounded training (20 or 250 iterations). They were not suppressed. Passing reconstruction gates does not establish optimizer convergence.

## Offline numeric experiment

The parent executed `scripts/ml_demo.py` in the shared project environment with `socket.socket.connect`, `connect_ex` and `socket.create_connection` replaced by raising guards before importing the workflow.

Observed report: `data/verified-ml-demo/report.json` (private generated output, Git-ignored).

| Measurement | Observed value |
|---|---|
| Run ID | `7fcf5755b5a74c688c2250d81e3dde85` |
| Stages | preprocess, train, evaluate, publish |
| Status | published in local MLflow registry |
| Registry version | 1 |
| Held-out reconstruction MSE | 0.0689430883037174 |
| Train-mean baseline MSE | 1.5349995985457274 |
| Dataset SHA256 | `1d3ef03f959838d5dd1f8b0b14a50c7dc5c57846d24d8328bb76fec79a887458` |

The data was a seeded low-rank numeric matrix plus noise. These values are **not voice quality, speaker similarity or TTS measurements**. The socket guard checks this Python execution path, not OS-wide egress or subprocess networking. No claim of host-wide network isolation is made.

## Review corrections and live HTTP check

Two independent review findings were reproduced with failing tests, then fixed: access logs could retain profile query metadata, and accepted IPv6 binding did not pass Host validation. Access logging is now disabled; the supported server binding is IPv4 loopback.

Post-fix checks: **85 passed, 7 warnings in 40.71 seconds**, Ruff clean, wheel rebuilt. Before the fixes, a parent-started real server returned `GET /health` 200 and `POST /speak` 503 with the explicit unavailable message. That 503 is an intentional capability boundary, not evidence of functioning synthesis.

A separate OpenVoice environment has since generated a real WAV under offline guards; see [OpenVoice evidence](openvoice-spike.md). It remains separate from the application.

## Remaining verification

- Dependency advisory audit and review of any later implementation changes.
- Real authorized speech synthesis and human listening assessment.
- Trained checkpoint reload/inference parity and connection to acoustic profile data.
- Persisted recording split manifests, recovery and consent withdrawal.
- Browser calibration and optional local service deployments.

The detailed phase exit gates remain unchecked until their own evidence exists.
