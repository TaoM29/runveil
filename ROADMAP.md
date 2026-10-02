# Roadmap

The [original charter](docs/PROJECT_PLAN.md) is the source of truth. Each phase must
be independently reviewed before the next begins. No automatic continuation,
commit or push is authorized.

| Phase | Scope                                                     | Status                                     |
| ----- | --------------------------------------------------------- | ------------------------------------------ |
| 0     | Charter, workspaces, health, quality tooling, Compose, CI | Implemented; see verification record       |
| 1     | Domain model, immutable versions, persistence, migrations | Implemented through Phase 1C               |
| 2     | Provider protocol, scripted and hosted providers          | Implemented; hosted acceptance complete    |
| 3     | Minimal persisted execution loop                          | Implemented; continued by Phase 4 request  |
| 4     | Typed tools and authorization                             | Implemented through Phase 4B               |
| 5     | Durable worker, retries, idempotency and budgets          | Complete; Phase 6 continuation authorized  |
| 6     | Human approval and controlled mutations                   | Complete; Phase 7 continuation authorized  |
| 7     | Telemetry and trace UI                                    | Complete; Phase 8 continuation authorized  |
| 8     | Deterministic evaluation harness                          | Complete; Phase 9 continuation authorized  |
| 9     | Statistical comparison                                    | Complete; Phase 10 continuation authorized |
| 10    | Sandboxed software engineering application                | Implemented through 10D; review pending    |
| 11    | MCP adapter through existing policy                       | Planned                                    |
| 12    | AWS infrastructure with Terraform                         | Planned                                    |
| 13    | Production CI/CD                                          | Planned                                    |
| 14    | Temporary self-hosted inference and benchmarks            | Planned                                    |
| 15    | Security hardening                                        | Planned                                    |
| 16    | Public demo and portfolio release                         | Planned                                    |

## Phase 1 review gates

- **1A — Implemented:** agent definitions; versions immutable from
  creation; persisted runs; validated lifecycle transitions and timestamps; expected
  revisions for concurrency; initial PostgreSQL migration; database readiness;
  deterministic unit and PostgreSQL integration tests. See the
  [verification record](docs/operations/PHASE_1A.md) and
  [ADR 0003](docs/adr/0003-phase-1a-persistence.md).
- **1B — Implemented:** ordered steps and execution events;
  atomic lifecycle history; versioned full checkpoint snapshots; stale-history
  checks, rollback/concurrency/restore tests and populated 1A migration tests. See
  [ADR 0004](docs/adr/0004-execution-history.md) and the
  [verification record](docs/operations/PHASE_1B.md).
- **1C — Implemented:** durable model-invocation and tool-call
  requests; one-time success/failure outcomes; same-run model provenance; atomic
  outcome/event/step/checkpoint recording; migration and integration tests. See
  [ADR 0005](docs/adr/0005-invocation-records.md) and the
  [verification record](docs/operations/PHASE_1C.md).

## Phase 2 review gates

- **2A — Implemented:** provider protocol, normalized versioned
  request/response contracts, usage and latency fields, structured action schema
  and validation, deterministic scripted responses/errors, and persistence
  round-trip verification. See [ADR 0006](docs/adr/0006-model-contracts.md),
  [model contract usage](docs/operations/MODELS.md) and the
  [verification record](docs/operations/PHASE_2A.md).
- **2B — Implemented; hosted acceptance complete:** hosted/OpenAI-compatible
  adapter, bounded HTTP transport, timeout/cancellation and safe error mapping,
  offline provider contract tests and an explicitly opt-in live command. See
  [ADR 0007](docs/adr/0007-hosted-provider.md) and the
  [verification record](docs/operations/PHASE_2B.md#subsequent-hosted-live-acceptance--complete)
  for the successful user-reported hosted invocation and safe acceptance evidence.

## Phase 3 review gate

- **Implemented; Phase 4 continuation authorized:** pinned runtime configuration, bounded execution
  loop, one fixed read-only fixture tool, ordered context, committed request intent,
  atomic outcomes/checkpoints/terminal transitions and database reconstruction.
  Integration coverage includes step limits, safe failures, stale results and
  cancellation. See [ADR 0008](docs/adr/0008-minimal-runtime.md),
  [runtime operations](docs/operations/RUNTIME.md) and
  [verification record](docs/operations/PHASE_3.md).
- Explicit Phase 3 authorization allowed offline work while the Phase 2 hosted
  live gate was pending. That gate is now complete through the separately reported
  hosted invocation, not the offline demo or tests.

## Phase 4 review gates

- **4A — Implemented; Phase 4B continuation authorized:** typed registry, strict bounded input/output
  validation, intersected pinned/operator grants, permission and side-effect
  classification, cooperative deadlines, safe errors and persisted dispatch through
  the registered fixture. See [ADR 0009](docs/adr/0009-typed-tool-dispatch.md) and
  [verification record](docs/operations/PHASE_4A.md).
- **4B — Implemented; Phase 5 continuation authorized:** native read/search tools with exact file
  allowlists, descriptor-relative containment, symlink/hard-link/special-file
  refusal, bounded UTF-8 reads and literal search, safe errors, cancellation cleanup
  and persisted integration. See [ADR 0010](docs/adr/0010-repository-read-tools.md),
  [operations](docs/operations/REPOSITORY_TOOLS.md) and
  [verification record](docs/operations/PHASE_4B.md).

## Phase 5 review gates

- **5A — Implemented; Phase 5B continuation authorized:** PostgreSQL work enrollment and polling,
  leased claims and transactional stale-worker fences, version-2 checkpoint resume,
  conservative failure of uncertain in-flight invocations, and duplicate delivery
  safety for a fixed scripted/fixture profile. See [ADR 0011](docs/adr/0011-durable-fixture-worker.md),
  [worker operations](docs/operations/WORKER.md) and [handoff](docs/operations/PHASE_5A.md).
  No general retries, broker, repository replay or expanded budgets are claimed.
- **5B — Implemented; Phase 5C continuation authorized:** bounded model retries for the opt-in
  `fixture-retry-v1` profile, atomic failed-attempt/schedule/RETRYING boundaries,
  database-clock backoff, new invocation provenance, due-time recovery and run-wide
  retry/step accounting. Existing profiles retain their behavior. See
  [ADR 0012](docs/adr/0012-persisted-model-retries.md), [operations](docs/operations/WORKER.md)
  and [handoff](docs/operations/PHASE_5B.md). Unknown/uncertain failures are not retried;
  hosted replay, tool retries and broader budgets remain deferred.

- **5C — Implemented; Phase 5D continuation authorized:** durable elapsed budget from first start,
  immutable deadline, budget checks at execution boundaries, cooperative call
  timeouts, expired-backoff cleanup and atomic budget failure. New offline
  `fixture-budget-v1` profile; existing profiles unchanged. See
  [ADR 0013](docs/adr/0013-durable-elapsed-budget.md), [operations](docs/operations/WORKER.md)
  and [handoff](docs/operations/PHASE_5C.md). This is not a hard real-time sandbox;
  live leases may delay crash cleanup.

- **5D — Implemented; Phase 5E continuation authorized:** durable reported input/output accounting,
  explicit unknown usage, atomic token failure, retry/recovery preservation and
  the offline `fixture-token-v1` profile. See [ADR 0014](docs/adr/0014-durable-token-budget.md)
  and [handoff](docs/operations/PHASE_5D.md). These are post-attempt stop thresholds;
  one call may cross a limit. No hard billing cap is claimed.

- **5E — Implemented; Phase 5F continuation authorized:** immutable linear USD pricing, exact
  integer cost estimates and post-attempt cost limits, including partial/uncertain
  usage, failed attempts, retries and recovery. New offline `fixture-cost-v1`
  profile. See [ADR 0015](docs/adr/0015-pinned-cost-budget.md) and
  [handoff](docs/operations/PHASE_5E.md). No invoice or hard spending-cap claim.

- **5F — Implemented; Phase 5G continuation authorized:** run-wide repeated-tool limit, pinned in
  version 7 and enforced against durable invocation history before creating the
  next tool intent. Atomic failure and restart-safe counting; offline
  `fixture-loop-v1` demonstrates a blocked third identical call. See
  [ADR 0016](docs/adr/0016-durable-repeated-tool-limit.md) and
  [handoff](docs/operations/PHASE_5F.md). No semantic loop inference or new side effects.

- **5G — Implemented; Phase 5H continuation authorized:** separate pinned model/tool intent limits,
  admission before dispatch, retry-capacity checks and conservative uncertain-intent
  accounting. New offline `fixture-calls-v1` succeeds exactly at both limits.
  See [ADR 0017](docs/adr/0017-durable-invocation-limits.md) and
  [handoff](docs/operations/PHASE_5G.md). The existing total-step bound remains active.

- **5H — Implemented; Phase 5I continuation authorized:** bounded immutable repository snapshots,
  version-9 workspace/tool implementation identity and explicit offline
  `repository-read-v1` worker recovery. Changed roots, allowlists, content or covered
  implementation refuse execution; clean checkpoints resume with identical bindings.
  See [ADR 0018](docs/adr/0018-pinned-repository-recovery.md) and
  [handoff](docs/operations/PHASE_5H.md). No durable content archive or tool replay.

- **5I — Implemented; Phase 5J continuation authorized:** opt-in transactional notification outbox,
  bounded SQS Standard relay/consumer for `fixture-calls-v1`, recurring eligible-work
  publication and terminal-state acknowledgement under existing database claims.
  Offline SDK/PostgreSQL evidence covers send/ack crash boundaries and duplicates.
  See [ADR 0019](docs/adr/0019-sqs-notification-outbox.md) and
  [handoff](docs/operations/PHASE_5I.md). No live AWS acceptance or provisioning.

- **5J — Implemented; Phase 5 acceptance continuation authorized:** three-rejection admission quarantine for
  `fixture-calls-v1`, cooldown and claim-fenced append-only audit, selection suppression
  across polling/outbox, and operator inspection/release with revision and binding checks.
  Runtime history, deadlines and uncertain-intent semantics remain unchanged.
  See [ADR 0020](docs/adr/0020-worker-admission-quarantine.md) and
  [handoff](docs/operations/PHASE_5J.md). Other failure classes/profiles are not auto-quarantined.

- **5K — Acceptance complete; ready for closure review:** one offline process-death
  command verifies SIGKILL, active-lease deferral, fresh-process checkpoint recovery,
  successful continuation, uncertain-intent failure without replay and terminal
  duplicate acknowledgement. CI runs it alongside the unchanged pytest suite.
  The [closure audit](docs/operations/PHASE_5.md) maps every Phase 5 criterion to
  implementation/evidence and explicit limits; see [handoff](docs/operations/PHASE_5K.md).

## Phase 5 closure

Phase 5 implementation and acceptance are complete within the accepted boundaries
of ADRs 0011–0020. No required criterion remains open for the supported profiles.
The charter's worker-crash/restart/recovery/success and duplicate-message gates are
now demonstrated across actual process death. Live AWS/IAM acceptance, deployment
operations, hosted retry safety and exactly-once external effects are not claimed.
The SQS target is offline verified; live infrastructure remains Phase 12, with live
acceptance a separate opt-in activity. Phase 6 continuation was authorized on
2026-10-01.

## Phase 6 review gates

- **6A — Implemented; Phase 6B continuation authorized:** durable single-file patch proposal,
  exact-content digest, atomic request/checkpoint/pause, revision-bound one-time
  approval or rejection and local inspection/decision CLI. Approval resumes to a
  persisted review result; rejection terminates. No patch is applied in this slice,
  and existing worker/runtime mutation denial remains intact. See
  [ADR 0021](docs/adr/0021-durable-patch-review.md),
  [operations](docs/operations/APPROVALS.md) and [handoff](docs/operations/PHASE_6A.md).
  This is an isolated review workflow, not model-driven worker recovery or full
  Phase 6 acceptance. HTTP/UI and controlled patch writing were deferred to later slices.

- **6B — Implemented; Phase 6C continuation authorized:** offline model-driven repository proposal,
  exact snapshot preimage validation, fenced atomic worker suspension/lease release,
  one-time decisions and checkpoint continuation under a fresh workspace binding.
  Approval wait preserves the original elapsed deadline and accounting; uncertain
  proposal intent fails without replay. Existing Phase 6A approvals remain separate.
  No patch writing, hosted acceptance, broker extension or API/UI is claimed. See
  [ADR 0022](docs/adr/0022-worker-patch-review.md),
  [operations](docs/operations/APPROVALS.md#workspace-bound-worker-review-phase-6b)
  and [handoff](docs/operations/PHASE_6B.md).

- **6C — Implemented; Phase 6D continuation authorized:** new write-capable profile and version 11,
  exact approved single-file replacement, separate operator WRITE grant, committed
  single-use intent, final claim/approval/preimage checks and atomic filesystem
  replacement. Uncertain intent terminates without filesystem access or replay;
  existing review-only approvals cannot authorize writes. Scope is one ordinary
  top-level file in an exclusively assigned trusted checkout, not a sandbox.
  See [ADR 0023](docs/adr/0023-controlled-single-file-mutation.md),
  [operations](docs/operations/PATCHES.md) and [handoff](docs/operations/PHASE_6C.md).

- **6D — Implemented; Phase 6E continuation authorized:** authenticated local operator HTTP inspection
  and approve/reject decisions across the three existing approval profiles.
  Exact proposal/workspace/mutation inspection, profile/ID/revision/digest binding,
  strict bounded requests and existing atomic resolvers preserve execution authority.
  No worker dispatch or WRITE grant, schema change or console is included.
  See [ADR 0024](docs/adr/0024-local-operator-approval-api.md),
  [operations](docs/operations/APPROVAL_API.md) and [handoff](docs/operations/PHASE_6D.md).

- **6E — Implemented; browser acceptance continuation authorized:** small single-run approval console with
  memory-only credentials, exact proposal/workspace/mutation inspection, explicit
  profile consequences and inspection-bound decisions. A bounded local proxy
  forwards caller authentication without acquiring write or worker-start authority.
  Stale responses are discarded; uncertain decisions require new inspection.
  See [ADR 0025](docs/adr/0025-local-approval-console.md),
  [operations](docs/operations/APPROVAL_CONSOLE.md) and [handoff](docs/operations/PHASE_6E.md).

- **6F — Acceptance complete; ready for closure review:** real-browser approval
  and rejection through the production console, API, PostgreSQL and fresh worker
  processes. Verified preapproval write prevention, explicit later execution,
  exact approved replacement, rejection/no mutation and persisted browser outcomes.
  No application changes or additional tests were needed. See
  [closure audit](docs/operations/PHASE_6.md) and [handoff](docs/operations/PHASE_6F.md).

## Phase 6 closure

Implementation and acceptance are complete within ADRs 0021–0025's documented
local operator and controlled single-file boundaries. The browser/worker evidence
closes the remaining Phase 6E gap; no required charter gate remains open in that
scope. Shared credentials, trusted checkout assumptions, uncertain side-effect
recovery and deferred hosted/remote/sandbox guarantees remain explicit.

Phase 7 continuation was authorized on 2026-10-01.

## Phase 7 review gates

- **7A — Implemented; Phase 7B continuation authorized:** separate read-only trace capability,
  consistent database snapshots, bounded ordered event pagination, invocation
  correlation/outcomes/durations, retry links, checkpoint token/cost accounting,
  approval metadata and bounded final summary. No execution/authorization changes.
  See [ADR 0026](docs/adr/0026-durable-run-trace.md),
  [operations](docs/operations/TRACES.md) and [handoff](docs/operations/PHASE_7A.md).
  Per-attempt usage/latency projection remains deferred.

- **7B — Implemented; Phase 7C continuation authorized:** operational single-run trace console,
  separate memory-only read credential, bounded GET proxy and watermark-bound
  event pages. Unknown accounting, persisted timing and approval limitations remain
  explicit. Browser verification covers completed/paused runs and 113-event
  pagination, with no mutation authority. See
  [ADR 0027](docs/adr/0027-local-trace-console.md), [operations](docs/operations/TRACES.md)
  and [handoff](docs/operations/PHASE_7B.md).
  Integrated acceptance is recorded in Phase 7D below.

- **7C — Implemented; acceptance/closure continuation authorized:** opt-in core execution/model/tool OTel spans,
  worker-owned bounded JSON stderr export and durable invocation/accounting
  correlation. Export failures preserve execution, retries and approval/WRITE
  boundaries. No persistence/API/UI changes or network collector. See
  [ADR 0028](docs/adr/0028-execution-telemetry.md),
  [operations](docs/operations/TELEMETRY.md) and [handoff](docs/operations/PHASE_7C.md).

- **7D — Acceptance complete; ready for closure review:** fresh completed, failed,
  retried and approval-wait workers, real authenticated API/proxy requests, direct
  database reconciliation, structured OTel output and production-browser inspection.
  Credential separation and read-only behavior preserve pending state and file bytes.
  No application changes or additional tests were needed. See
  [closure audit](docs/operations/PHASE_7.md) and [handoff](docs/operations/PHASE_7D.md).

## Phase 7 closure

Implementation and acceptance are complete within ADRs 0026–0028's documented
local scope. API/UI evidence and opt-in spans correlate with persisted runtime
records; no required charter acceptance gate remains open in this scope. Shared
local capabilities, content-minimized projections, persisted timing semantics,
unknown accounting and best-effort telemetry limits remain explicit. Per-attempt
UI usage/provider latency, collectors and public deployment remain deferred.

Phase 8 continuation was authorized on 2026-10-01.

## Phase 8 review gates

- **8A — Implemented; Phase 8B continuation authorized:** immutable versioned suite/case contracts,
  PostgreSQL-backed scripted execution, deterministic scoring from persisted evidence,
  EvalRun/case-result JSON snapshots, full provenance and paired aggregate comparison.
  Three public code-reading calibration cases compare two immutable step budgets;
  this validates the harness, not model quality. No schema, runtime, authorization,
  telemetry or UI change. See [ADR 0029](docs/adr/0029-offline-evaluation-harness.md),
  [operations](docs/operations/EVALUATIONS.md) and [handoff](docs/operations/PHASE_8A.md).

- **8B — Implemented; acceptance/scope audit authorized:** a frozen 24-case controlled code-reading
  corpus across eight subjects, with disjoint 16-case development and 8-case held-out
  partitions, explicit CLI selection, content digests and reviewed answer rationales.
  Existing claimed execution/scoring compares both step budgets within each partition;
  reports cannot mix splits. The original calibration remains available. This is
  scripted harness evidence, not model quality, hidden holdout or code repair evidence.
  See [ADR 0030](docs/adr/0030-controlled-code-reading-benchmark.md),
  [benchmark inventory](docs/operations/BENCHMARK.md) and [handoff](docs/operations/PHASE_8B.md).

- **8C — Acceptance complete; ready for closure review:** retained report content and
  independent arithmetic audit, fresh reproduction of both partitions, direct database
  reconciliation of 48 runs, comparison/CLI refusal checks and existing evaluation tests.
  No implementation, benchmark or test changes. Claims about human review and exact
  budget use were clarified. See [closure audit](docs/operations/PHASE_8.md),
  [evidence](docs/operations/evidence/phase8c/audit.json) and [handoff](docs/operations/PHASE_8C.md).

## Phase 8 closure

The initial harness, versioned 24-case code-reading corpus and reproducible fixed
agent-version comparison gate are complete within ADRs 0029–0030's offline scripted
scope. Public held-out partitions are tuning conventions, not blind model evaluations.
General provider selection, generated code/test execution, regression-safety metrics
and full product-level evaluation claims remain outside this closure. No model quality
or statistical significance is demonstrated by the constructed budget effects.

Phase 9 continuation was authorized on 2026-10-01.

## Phase 9 review gates

- **9A — Implemented; acceptance/scope audit authorized:** opt-in statistical wrapper over the existing
  guarded comparison, exact paired percentile bootstrap for binary success deltas,
  elapsed/cost summaries and failure categories. Synthetic exhaustive-resampling
  oracles and durable evaluation acceptance verify method and boundaries. Scripted
  evidence remains descriptive, with no model-quality or significance verdict.
  See [ADR 0031](docs/adr/0031-exact-paired-statistics.md),
  [methodology](docs/operations/STATISTICS.md) and [handoff](docs/operations/PHASE_9A.md).

- **9B — Acceptance complete; ready for closure review:** independent multinomial
  oracle for all 5,455 bounded outcome histograms, retained report arithmetic and
  identity audit, fresh repeated reports across all three suites, 114 direct database
  reconciliations, comparison/CLI refusals and existing evaluation tests. No
  implementation, benchmark or test change. See [closure audit](docs/operations/PHASE_9.md),
  [evidence](docs/operations/evidence/phase9b/audit.json) and [handoff](docs/operations/PHASE_9B.md).

## Phase 9 closure

The paired statistical-method gate is complete within ADR 0031's bounded scripted
scope. Exact empirical percentile intervals, success deltas, descriptive elapsed/cost
summaries, failure categories and reproducible reports are verified. This does not
establish model quality, population coverage, significance or an automatic regression
gate. Real stochastic evaluation design and broader provider selection remain future work.

Phase 10 continuation was authorized on 2026-10-02.

## Phase 10 review gates

- **10A — Implemented; Phase 10B continuation authorized:** operator-only disposable Docker fixture
  execution with an immutable image ID, fixed test command, bounded resources/output,
  isolated tmpfs workspace and verified cleanup. A buggy coding fixture and separate
  isolation/timeout/output probes establish the boundary. Existing runtime EXECUTE
  denial, approvals, durability, traces and evaluation behavior remain unchanged.
  See [ADR 0032](docs/adr/0032-disposable-fixture-sandbox.md),
  [operations](docs/operations/SANDBOX.md) and [handoff](docs/operations/PHASE_10A.md).
  This does not close Phase 10's agent-driven coding acceptance gate.

- **10B — Implemented; Phase 10C continuation authorized:** pinned `sandbox-tests-v1` worker with a
  narrow `tests.run` EXECUTE capability, explicit operator grant, existing durable
  intent/outcome/checkpoint/accounting and pre-create/pre-start ownership checks.
  Clean checkpoints resume; uncertain intent terminates without Docker or replay.
  A fresh worker runs the real clamp baseline and persists its failed-test observation.
  General tool dispatch remains read-only and patch approvals are unchanged.
  See [ADR 0033](docs/adr/0033-durable-sandbox-execution.md),
  [operations](docs/operations/SANDBOX.md#durable-sandbox-tests--phase-10b) and
  [handoff](docs/operations/PHASE_10B.md). No repaired-task or full Phase 10 closure claim.

- **10C — Implemented; Phase 10D continuation authorized:** separate `sandbox-review-v1` worker,
  bounded in-container fixture inspection, exact recorded preimage validation,
  independent durable proposal provenance checks and existing human review pause.
  Local inspection exposes immutable identity, exact before/after, hashes and diff;
  approval finishes review without applying a patch. Clean recovery reuses evidence;
  uncertain inspection/proposal intent fails without replay. See
  [ADR 0034](docs/adr/0034-sandbox-inspection-review.md),
  [operations](docs/operations/SANDBOX.md#sandbox-inspection-and-exact-review--phase-10c)
  and [handoff](docs/operations/PHASE_10C.md).

- **10D — Implemented; review pending:** distinct `sandbox-patch-v1` profile with
  explicit execution-time WRITE/EXECUTE grants, exact approved single-use mutation
  intent, fresh full workspace/preimage checks and bounded in-container tests.
  Durable outcomes retain approved diff, workspace digests and test observations;
  failed validation stays inspectable. Unknown mutation outcomes terminate without
  adapter construction or replay. Review-only approvals remain non-writing.
  See [ADR 0035](docs/adr/0035-approved-sandbox-patches.md),
  [operations](docs/operations/SANDBOX.md#approved-sandbox-patch-and-validation--phase-10d)
  and [handoff](docs/operations/PHASE_10D.md).

## Recommended next slice

Review 10D, then extend the controlled fixture/task selection deliberately to several
small repairs with explicit pinned identities and independent end-to-end acceptance.
Audit remaining Phase 10 search and failed-task inspection requirements before
claiming closure. Preserve approval/WRITE separation and no-replay mutation recovery.
No automatic continuation is authorized.
