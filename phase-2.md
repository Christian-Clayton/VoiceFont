# Phase 2: real local ML and reproducible orchestration

**Status: planned.** Implementation specification for contributors with [Phase 1](phase-1.md) complete. This is the first trainable ML deliverable, not a speech backend.

## Outcome

Train a small acoustic representation autoencoder on locally available authorized audio, measure held-out reconstruction loss, save and reload actual learned weights, and orchestrate the experiment with LangGraph and local MLflow tracking. No Docker or pretrained voice model is required.

## Model and data contract

Use a fixed-size acoustic representation with documented extraction parameters, normalization and input shape. Recommend a compact feed-forward autoencoder over fixed-length log spectral features for a bounded CPU experiment. Freeze the initial representation version before comparing runs. The decoder reconstructs features, not text-conditioned speech. Embeddings may encode recording conditions and content rather than speaker identity.

Split at original recording or session group level before windowing or augmentation. All windows and augmented copies of a source stay in the same split. Fit normalization on training data only. Persist train/validation/test manifests, source hashes, split seed and grouping rule. If the corpus cannot provide independent held-out groups, reject a generalization claim and mark the run an engineering smoke test.

Synthetic audio is acceptable for deterministic optimizer/plumbing tests if explicitly labeled. Showcase speech-representation conclusions require owned or authorized speech and a dataset card. No downloads during training or test discovery.

## Increments

| ID | Proposed files | Behavior change | Test first / verification | Dependency and risk |
|---|---|---|---|---|
| 2.1 | ML features/dataset modules and split tests | Create versioned features and leakage-safe manifests | Duplicate-source groups cannot cross splits; held-out data cannot change fitted normalization | Phase 1; leakage invalidates loss claims |
| 2.2 | ML model/training modules and tests | Train compact autoencoder with bounded epochs, seed and checkpoint | Actual optimizer step changes parameters; non-finite loss aborts; reload reproduces predictions | 2.1; begin CPU with a tiny fit test |
| 2.3 | Evaluation module and report tests | Compare trained, untrained and train-mean predictors on identical held-out inputs | Corrupt checkpoint/preprocessing mismatch fails; validation selection differs from test evaluation | 2.2; loss is not perceptual quality |
| 2.4 | Proposed `src/voicefont/pipeline/`, graph state tests | Run preprocess -> train -> evaluate -> deploy in LangGraph | Rejected evaluation never reaches promotion; failed node records error and bounded retry | 2.3; side effects must be idempotent |
| 2.5 | Local tracking adapter, promotion registry and integration tests | MLflow lineage, artifact registration and rollback | Offline run records real metrics; promotion is atomic; previous active version survives failure | 2.4; verify pinned MLflow behavior |

## Graph state and promotion

Graph state carries run ID, configuration hash, dataset manifest hash, feature/model versions, local artifact paths, stage status, measured metrics and an explicit evaluation decision. Store large tensors/audio outside graph state. Checkpoint state locally. Resume must verify upstream artifacts before reusing a successful stage; changed inputs produce a new run. Cap retries and training time.

Initial `deploy` means atomically promoting an approved model version in a local filesystem registry. No server or cluster is required. Require finite losses, valid artifact checksums, no detected split leakage, and held-out improvement over the untrained baseline. For a showcase model, also require improvement over the train-mean predictor. If that fails, preserve and report the negative result instead of adjusting the test set or claiming a useful embedding.

Select checkpoints/hyperparameters using validation data. Evaluate the selected candidate on a separate test split once for the reported experiment. Very small fixture tests can use a train/held-out split but must not be described as a rigorous model benchmark. Define comparison tolerance and candidate policy in versioned configuration before evaluation.

MLflow records epoch loss, validation loss, final test loss, baselines, seed, hyperparameters, training time, data counts, library versions, model/preprocessing hashes and promotion decision. Use local artifacts plus a supported local tracking store; verify the pinned MLflow version before choosing filesystem or SQLite semantics. Audio artifacts remain private and require explicit inclusion. Disable telemetry and external tracing.

## Acceptance criteria

- [ ] A real CPU training run updates weights, logs loss history, writes a checkpoint and reloads it for held-out inference.
- [ ] Reports identify acoustic reconstruction, distinguish smoke data from speech data, and include baseline losses and split counts.
- [ ] No source recording or derivative leaks across groups; training normalization is reused unchanged for validation/test.
- [ ] A successful graph run and deliberately rejected candidate produce local MLflow evidence. Rejection leaves the previous active artifact untouched.
- [ ] An interrupted run resumes without duplicating side effects; changed or corrupt upstream artifacts cause controlled failure or a new run.
- [ ] Native offline tests pass without Docker, CUDA, OpenVoice weights, hosted APIs or automatic dependency fetching.

## Resource and scientific limits

Begin with a small parameter count, batch and dataset. Record peak RAM, wall time and parameter count; do not promise runtime until measured. Tune within a bounded CPU budget. A 6 GB GPU is an optional speed experiment, not a reason to enlarge the baseline.

Held-out reconstruction loss and embedding similarity do not prove speech identity, accent fidelity, intelligibility or cloning quality. [Phase 5](phase-5.md) has separate provisioning/listening gates. [Phase 7](phase-7.md) later exports this trained acoustic model to Triton.
