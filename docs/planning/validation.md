# Validate claims separately from plans

**Document type:** reference for implementers and reviewers. **Status:** required future verification protocol, not a report that application tests have run. The documentation-only audit is recorded in [revision record](revision-record.md).

## Evidence record

For every claimed capability retain: date, tested source revision or workspace hash, platform, interpreter, dependency/weight/image versions, command, exit status, suite counts (passed/failed/skipped), data provenance, local run IDs, artifact hashes, observations and limitations. Record private evidence under the owner's local data root; publish only approved redacted reports.

Statuses are `planned`, `implemented-unverified`, `verified-on-platform`, `blocked` and `deferred`. Only actual execution plus the relevant acceptance criteria permits verified status. A renderer, mock adapter or skipped test cannot verify a real external service. This revision does not populate an implementation capability matrix.

## Test tiers and expected outputs

| Tier | Prerequisites | Required proof | Does not prove |
|---|---|---|---|
| Native numerical/unit | Provisioned Python 3.11 CPU environment | Audio/profile errors, optimizer updates, split rules, checkpoint parity, local CLI behavior | Speech synthesis or service compatibility |
| Native ML integration | Local training/tracking dependencies and declared data | Real train/evaluate/promote, local MLflow metrics and graph recovery | Useful speaker identity or TTS |
| Browser calibration | Bundled UI, local server and browser; mic for manual check | Real capture, codec handling, re-record and restart-safe finalization | Actual phonemes/emotions from intended prompt tags |
| Real speech integration | Pinned permitted local OpenVoice/base TTS resources and authorized reference | Actual new speech, human listening notes and measured latency | Identity verification or universal profile compatibility |
| Local vector service | Provisioned self-hosted Weaviate | Explicit vector insert/query, filters, version isolation and withdrawal | Relevance from self-match alone |
| Serving/deployment | Running local engine, cached images, local cluster/providers | Native/ONNX/Triton parity, Helm lifecycle and Terraform no-op second plan | GPU support from CPU execution or deployment from static validation |
| Streaming | Verified real speech/client | Correct framing/order, early playable sentence and bounded cancellation behavior | Generation latency improvement from early headers |

The intended Python suite command is the selected environment's `python -m pytest`; implementers must record its actual environment path and output. New named tests in the phase tables are specifications, not assertions those files already exist. Add local lint/type/build gates only after actual project tooling is selected and checked. Container/Kubernetes tests are explicit opt-in suites that fail when requested prerequisites are absent, rather than silently reporting success.

## Offline acceptance

1. Provision dependencies, model resources, images, chart dependencies and provider binaries in a separate approved step. Record source, version, hash, license and local cache location. A free download is not an ongoing runtime dependency.
2. Disable telemetry, tracing exports, crash uploads, update checks and hosted vectorization in each pinned component. Inspect actual settings, not assumed defaults.
3. Test native execution with outbound network unavailable. For loopback/Compose/cluster suites, permit only the required local traffic and block public egress. Account for local DNS and bridge networks without opening public destinations.
4. Observe attempted outbound traffic as well as failures. A blocked telemetry attempt is still an offline-policy failure to fix. Native socket guards help but do not cover subprocesses/containers; use appropriate host/network evidence too.
5. Run commands from a clean working directory with provisioned caches only. A missing package/weight must produce an actionable error and no attempted download.
6. Repeat with optional services stopped to prove the native boundary. Report OS firewall or packet-monitoring gaps as verification limits rather than claiming zero egress without evidence.

No cloud CI jobs, hosted test services, paid APIs or free-tier cloud resources may be used. Documentation linting can run locally. Upstream source/license review during approved provisioning is distinct from runtime/testing.

## Scientific checks

- Declare task, feature version and data provenance. Use recording/session-group splits before windows or augmentation; train-only normalization.
- Record real initial/final weights or parameter-change checks, losses and checkpoint inference. Compare held-out trained, untrained and train-mean losses.
- Separate model-selection validation from final test evaluation. If the corpus only supports smoke testing, say so. Never relabel generated tones as a speech dataset.
- For retrieval, use independent queries and declared relevance labels. Report corpus size, embedding model, metric, filters and per-query results.
- For speech, retain actual outputs privately and separate human intelligibility, resemblance, style and naturalness judgments from signal metrics.
- For performance, report sample count, cold/warm state, cache policy, device, duration, first playable audio and total time. Unsupported GPU speed estimates are not results.

## Safety and lifecycle checks

Use disposable fixtures for corrupted profiles, oversized/malformed audio, interrupted writes, stale indexes, path traversal, unsupported schemas, revoked consent, interrupted training and service loss. Preserve raw hashes across processing/re-recording. Restrict checkpoint loading to trusted local artifacts and avoid unrestricted unsafe deserialization of user-supplied model files.

Prove that profile relocation works without original absolute paths. Backup and restore raw files, profile metadata, dataset manifests, tracking records and selected checkpoints. Withdrawal blocks use immediately and requires a plan for affected learned artifacts, caches and backup retention. Delete personal data only with explicit owner approval.

## Documentation gate

- [ ] Ten active plan files have coherent phases and unchecked acceptance criteria.
- [ ] Original bytes and hashes match the archive manifest; conversation.md remains unchanged.
- [ ] Every active document link resolves. Proposed source paths are clearly marked as proposed.
- [ ] Authored planning text contains no em dash and no fabricated completion record.
- [ ] Cloud references only explain exclusions or historical changes; there are no active cloud provisioning instructions.
- [ ] Native acoustic training, real speech and optional service verification are unmistakably separate.
- [ ] Any unsupported or deferred feature is visible, not hidden by a successful unit-test count.
