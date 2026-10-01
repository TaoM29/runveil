# Phase 8 acceptance and scope audit

**Acceptance complete for the offline, scripted, read-only scope of ADRs 0029–0030;
ready for closure review.** Audited 2026-10-01 at `2e385b8`. This closes the initial
harness/controlled code-reading comparison gate, not the charter's eventual
model-quality, code-repair or regression-safety ambitions. No implementation or test
change was required. No benchmark content, scripts, budgets or split membership changed.

## Charter-to-evidence assessment

| Requirement                           | Implementation and verification                                                                                                                                                                                                                                                                                    | Scope judgment                                                                                                                                                                                                                                                   |
| ------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| EvalSuite / EvalCase                  | Frozen bounded contracts contain task, public fixture, script, exact answer and ordered tool-name oracle. Existing tests verify unique IDs/content and immutable contracts.                                                                                                                                        | Implemented for built-in public cases; no arbitrary dataset/grader loader.                                                                                                                                                                                       |
| EvalRun / EvalCaseResult              | Reports contain batch identity, immutable agent version/configuration, source/dependency fingerprint, timestamps, run IDs, grades, errors and accounting. Underlying execution is persisted in PostgreSQL.                                                                                                         | Implemented as local report snapshots, not evaluation database tables or a resumable scheduler; ADR 0029 explicitly chooses this boundary.                                                                                                                       |
| Benchmark versioning                  | Canonical suite digest covers version, scorer, split, ordered membership, source, tasks, scripts and expected answers. Retained suite contents/digests match current definitions, including unchanged 8A calibration.                                                                                              | Content identity is stronger than a label. Version bumps and historical retention remain a review rule, not a repository-wide immutable dataset service.                                                                                                         |
| Deterministic scoring                 | Read-only consistent terminal-state reconstruction requires runtime success, exact final summary and ordered successful tool names. Fresh grades were independently recomputed from raw run/checkpoint/tool rows. Existing negative tests cover wrong answers, missing reads, traversal and unadvertised mutation. | Validates harness outcomes. Scripted answers are derived from the same declared oracle; they do not independently prove oracle correctness or model competence. Source rationales were inspected, not certified by a human panel or executable reference solver. |
| Agent-version comparison              | Two distinct persisted versions differ only in max_steps 3 versus 5. Within each partition they receive identical tasks, fixtures and scripts; no failed case is dropped.                                                                                                                                          | Meets the initial v1/v2 comparison gate through a controlled configuration change. A general version selector or hosted-provider run is not required by that gate and is not implemented.                                                                        |
| Initial 20–30 controlled coding cases | 24 code-reading cases in eight subject areas, partitioned into 16 development and 8 held-out; the separate three-case calibration is not counted toward 24.                                                                                                                                                        | Meets the agreed code-reading corpus size. It does not satisfy generated repair/test execution or the broader charter's coding task-success/regression-safety metrics. Those remain sandbox-dependent product work.                                              |
| Development / held-out discipline     | Disjoint case IDs, full source and questions; explicit held-out CLI selection; split is hashed; mixed/relabelled partitions fail comparison. Each report has one complete denominator.                                                                                                                             | Separation is real, but public scripts/answers are known. It is a tuning convention, not access control, blindness or proof against contamination. No actual held-out model evaluation occurred.                                                                 |
| Reproducible comparison report        | Fresh CLI runs for both partitions reproduce retained per-case grades, errors, event positions, steps, counts, retries and accounting. Implementation fingerprints agree with 8B. IDs, timestamps and elapsed times are excluded deliberately.                                                                     | Reproducible deterministic fields, not byte-identical reports or portable timing. Repeats are not new independent benchmark samples.                                                                                                                             |
| Aggregate metrics                     | Retained report sums/rates/deltas were independently recomputed from JSON case fields, including failures and unknown-accounting counters. Fresh raw rows reconcile configuration, status, grading, counts and accounting.                                                                                         | Counts, success rate, failure categories, steps, retries, elapsed sums and synthetic token/cost totals are supported. No invoice, latency quantile, confidence interval or significant improvement claim.                                                        |

The charter's Phase 8 list and initial comparison gate are met within the accepted
ADRs' local scope. The charter's wider metrics list also includes test/regression
success, valid-tool-call rate, p50/p95 timing and cost per successful task; the
current report does not expose all of them. Do not imply that this closure completes
all evaluation requirements across the product. Phase 9 covers statistical reporting;
Phase 10's sandbox is needed before executing generated coding tasks. Broader provider
selection remains a future capability, not an undisclosed blocker to this fixed
scripted acceptance. No later phase is authorized by this audit.

## Evidence and results

The audit uses the original retained [calibration](evidence/phase8/calibration.json),
[development](evidence/phase8b/development.json), [held-out](evidence/phase8b/held-out.json)
and [8B acceptance record](evidence/phase8b/acceptance.json), plus a new
[closure audit record](evidence/phase8c/audit.json). Historical files were not rewritten.
Their file SHA-256 values are recorded so the audited inputs can be identified.

| Suite / split              | Baseline pass count | Candidate pass count | Steps   | Model intents | Tool intents |
| -------------------------- | ------------------- | -------------------- | ------- | ------------- | ------------ |
| Calibration / development  | 2/3                 | 3/3                  | 7 → 9   | 5 → 6         | 2 → 3        |
| Code-reading / development | 8/16                | 16/16                | 48 → 64 | 32 → 40       | 16 → 24      |
| Code-reading / held-out    | 4/8                 | 8/8                  | 24 → 32 | 16 → 20       | 8 → 12       |

Fresh execution of both larger partitions created 48 runs. Direct database inspection
reconciled all 48 with their report configurations, terminal states, checkpoint
steps/errors/tokens/costs and invocation counts. It independently graded the raw
final summaries and ordered tool outcomes without calling the production scorer.
Both CLI refusals left the count at 48: unsupported calibration/held-out selection
exited 2 before output creation; an existing report path exited 1 without overwriting.

The eight exercised comparison refusals are: different split, relabelled split,
changed source, missing case, reordered cases, implementation mismatch, reused run ID
and identical agent-version ID. Existing tests additionally cover suite-digest
mismatch and execution/agent-version binding during rescoring. No guard is represented
as authentication of an adversarially constructed report.

Both controlled baselines fail only search-then-read cases with
`step_limit_exceeded`. Those candidate cases consume exactly five steps; read-only
single-read cases consume three under either budget. Known usage is synthetic,
unknown counters are zero for this corpus, and estimates use the pinned synthetic
tariff. The rate increase is a designed budget effect. No model, prompt or tool policy
was tuned using held-out results during this audit.

The historical 8A implementation fingerprint differs from current 8B source, as
expected; its suite remains unchanged and internally consistent. It is not evidence
that 8A and 8B measurements can be paired across implementation versions. The 8B
fingerprint equals the current implementation used for fresh closure execution.
Fingerprints do not pin the database image, OS, hardware or every transitive library.

## Claim corrections and trust boundaries

Two documentation statements needed precision, not code changes. ADR 0030 called
rationales “Human-reviewed” without retained evidence of independent human sign-off;
it now says source-reviewed and identifies that limitation. The benchmark guide
implied all five-step candidates consumed exactly five steps; that applies only to
search-then-read cases and is now explicit.

`Comparison.model_validate_json` validates shape/types, not all semantic invariants.
`compare` checks suite/implementation/coverage/identity and recalculates aggregates;
it still trusts supplied case grades and metadata. This slice exposes no untrusted
report-import service. Recomputing totals cannot authenticate an edited artifact or
prove its execution history. The authoritative raw database was inspected during
acceptance; the disposable audit database is removed afterward. Retained IDs and
selected fresh results are evidence references, not currently resolvable live traces.
The older 8B repeat's full report/database was not retained; its JSON record is an
attestation of that earlier check, supplemented here by fresh reproduction.

Exact tool-name order is not an oracle for arguments, search quality, source
understanding or model reasoning. Source answers and scripts share their expected
values, so a corpus-wide pass cannot independently validate those answers. Manual
assistant source inspection agrees with the published rationales; no fixture code
was imported/executed to strengthen that claim. Human review remains the purpose of
this handoff, not an acceptance event asserted retroactively.

Existing policy, claims, budget enforcement, uncertainty handling and telemetry are
unchanged. A batch failure can leave committed runs and an empty/partial output;
there is no resume/replay promise. Successful scripted runs do not replace prior
security, crash-recovery or approval tests. Paid providers, AWS, browser behavior,
statistical inference and sandboxed writes were not exercised or expanded.

## Closure recommendation

Accept Phase 8's documented scripted harness and controlled code-reading scope,
with the above boundaries preserved in any public claims. No implementation defect
requiring a change was found in that scope. Review this closure before separately
authorizing the first focused Phase 9 statistical-method slice; synthetic fixtures
may validate statistics, but cannot support a claim of real model improvement.
See the [8C handoff](PHASE_8C.md) for exact commands, files and verification gaps.
