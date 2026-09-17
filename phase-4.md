# Phase 4: adaptive calibration and local voice search

**Status: planned.** Implementation specification after [Phase 2](phase-2.md) and [Phase 3](phase-3.md). The adaptive selector can start when Phase 3 events are stable; learned-vector search requires Phase 2 artifacts.

## Outcome

Reduce unnecessary recording prompts through auditable gap targeting and find similar authorized references through versioned vectors. Neither a coverage score nor a similarity result authenticates a speaker.

## Increments

| ID | Proposed files | Behavior change | Test first / verification | Depends on / risk |
|---|---|---|---|---|
| 4.1 | Adaptive selector, policy configuration and tests | Rank eligible prompts by documented missing-coverage gain and recording effort | Same state/seed gives same choice; completed, rejected-ineligible and skipped prompts obey policy | Phase 3; heuristic gain is not trained item-response theory |
| 4.2 | Stop policy, session/UI integration | Offer early finish with reason and remaining gaps | Hard cap, minimum evidence, plateau and manual stop have distinct outcomes; repeated status reads do not advance selection | 4.1; plateau is not sufficient coverage |
| 4.3 | Embedding/export and native search modules | Produce model-versioned vectors and exact cosine ranking | Zero/non-finite/wrong-dimension vectors rejected; stable tie ordering; revoked profiles filtered | Phase 2 and profile contract; reconstruction embeddings can reflect noise/content |
| 4.4 | Optional Weaviate adapter and contract tests | Match native search/filter semantics in self-hosted Weaviate | External vectors supplied explicitly; no vectorizer call; metadata round-trip and version filtering agree | 4.3 and local service; Docker absence blocks integration only |
| 4.5 | Evaluation reports | Compare fixed/adaptive session efficiency and search relevance | Replayed accepted-take history yields the same coverage and ranking | 4.2 and 4.4; simulated efficiency is not human-study evidence |

## Adaptive policy

Use one authoritative stop policy. Bound maximum prompts and elapsed time. Minimum evidence may gate an automated sufficient-coverage recommendation but never prevent a person from stopping. Distinguish `coverage_sufficient`, `plateau_with_gaps`, `corpus_exhausted`, `time_limit`, `prompt_limit` and `user_stop`. Show remaining missing dimensions in every incomplete outcome.

Score intended coverage gain separately from observed quality improvement. Log policy version, candidate IDs, score components, selected prompt, seed and actual accepted-take gain. Do not count predicted gain as measured gain. Current-prompt reads must be side-effect free. Rejected takes and re-records use the Phase 3 accepted-take model.

Compare fixed and adaptive replay on the same authorized recorded corpus with the same target inventory. Record prompts used, accepted duration and each coverage component. Retain fixed mode as a fallback. Claims about faster human sessions require a separate local, voluntary comparison; do not promise that adaptive always wins.

## Vector storage contract

Native exact search is the reference implementation and works without a server. Each vector record includes profile/version, reference hash, consent scope/status, optional user-supplied language/style, embedding model hash, preprocessing version, dimension and local artifact identifier. Do not infer gender or other personal traits from audio.

For Weaviate, disable vectorization and generative modules. Supply vectors through the client's explicit object vector argument or a configured named-vector field, not a property with data type `vector`. Configure the pinned server/client pair together. Ordinary properties hold metadata only. Use a separate collection or enforced partition for each incompatible embedding space. Queries are vectors computed locally with the exact matching model/preprocessor. Reindex on model change and never compare mixed dimensions or versions.

Sample references are private local IDs, not public URLs. Search is limited to an enrolled, consented collection. Withdrawal must remove/filter records and prevent stale indexes or caches from returning revoked profiles. Keep only user-provided metadata needed for the feature.

## Acceptance criteria

- [ ] Deterministic adaptive tests cover missing dimensions, empty candidates, skip/retry, rejection, resume, minimum/cap conflicts and plateau with gaps.
- [ ] A replay report compares fixed/adaptive accepted duration and coverage without treating prompt tags as observed speech.
- [ ] Native search returns reproducible top-k results with documented cosine convention and ties; empty collection and incompatible versions fail or return explicit empty results.
- [ ] Optional local Weaviate ingestion/query returns the same nearest self-match and filter behavior as exact search on a small fixed corpus. Record any approximate ranking differences.
- [ ] Relevance evaluation uses independently recorded queries and owner-labeled expected relevance. Report per-query rankings and aggregate retrieval metric; self-match alone is not relevance evidence.
- [ ] Revoked consent and deleted-profile fixtures cannot be retrieved, including through stale cache paths.
- [ ] Offline execution makes no hosted vectorizer, language model or telemetry calls. Weaviate integration is reported blocked, not passed, when no local engine runs.

**Handoff:** search adapter can move to Compose in [Phase 7](phase-7.md). Adaptive calibration does not wait for Kubernetes or real TTS. Unrelated cognitive-organism material from the original Phase 4 is preserved only in the archive.
