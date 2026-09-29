# Roadmap

The [original charter](docs/PROJECT_PLAN.md) is the source of truth. Each phase must
be independently reviewed before the next begins. No automatic continuation,
commit or push is authorized.

| Phase | Scope                                                     | Status                                    |
| ----- | --------------------------------------------------------- | ----------------------------------------- |
| 0     | Charter, workspaces, health, quality tooling, Compose, CI | Implemented; see verification record      |
| 1     | Domain model, immutable versions, persistence, migrations | Implemented through Phase 1C              |
| 2     | Provider protocol, scripted and hosted providers          | Implemented; hosted acceptance complete   |
| 3     | Minimal persisted execution loop                          | Implemented; continued by Phase 4 request |
| 4     | Typed tools and authorization                             | Implemented through Phase 4B              |
| 5     | Durable worker, retries, idempotency and budgets          | Acceptance complete; closure review       |
| 6     | Human approval and controlled mutations                   | Planned                                   |
| 7     | Telemetry and trace UI                                    | Planned                                   |
| 8     | Deterministic evaluation harness                          | Planned                                   |
| 9     | Statistical comparison                                    | Planned                                   |
| 10    | Sandboxed software engineering application                | Planned                                   |
| 11    | MCP adapter through existing policy                       | Planned                                   |
| 12    | AWS infrastructure with Terraform                         | Planned                                   |
| 13    | Production CI/CD                                          | Planned                                   |
| 14    | Temporary self-hosted inference and benchmarks            | Planned                                   |
| 15    | Security hardening                                        | Planned                                   |
| 16    | Public demo and portfolio release                         | Planned                                   |

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
acceptance a separate opt-in activity. Stop for closure review before Phase 6.

## Recommended next slice

After review and separate authorization, begin Phase 6A: durable approval requests
and pause/resume for one controlled patch proposal. Establish that no patch is
applied before required approval and rejection prevents action; keep mutation
gated until that boundary exists and is reviewed. No Phase 6 implementation is
included in the Phase 5 completion work.
