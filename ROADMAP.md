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
| 4     | Typed tools and authorization                             | 4B implemented; awaiting review           |
| 5     | Durable worker, retries, idempotency and budgets          | Planned                                   |
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
- **4B — Implemented, awaiting review:** native read/search tools with exact file
  allowlists, descriptor-relative containment, symlink/hard-link/special-file
  refusal, bounded UTF-8 reads and literal search, safe errors, cancellation cleanup
  and persisted integration. See [ADR 0010](docs/adr/0010-repository-read-tools.md),
  [operations](docs/operations/REPOSITORY_TOOLS.md) and
  [verification record](docs/operations/PHASE_4B.md).

## Recommended next slice

Review Phase 4B, then plan the first Phase 5 durable execution slice: worker
ownership/claims, checkpoint resume and duplicate-delivery safety for scripted
model/fixture runs. Establish workspace and tool implementation identity before
replaying repository operations. Introduce queue/retry/budget work in coherent
reviewable increments; keep mutations, approvals and MCP in their planned phases.
