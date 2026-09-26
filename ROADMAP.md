# Roadmap

The [original charter](docs/PROJECT_PLAN.md) is the source of truth. Each phase must
be independently reviewed before the next begins. No automatic continuation,
commit or push is authorized.

| Phase | Scope                                                     | Status                                |
| ----- | --------------------------------------------------------- | ------------------------------------- |
| 0     | Charter, workspaces, health, quality tooling, Compose, CI | Implemented; see verification record  |
| 1     | Domain model, immutable versions, persistence, migrations | Phase 1C implemented; awaiting review |
| 2     | Provider protocol, scripted and hosted providers          | Planned                               |
| 3     | Minimal persisted execution loop                          | Planned                               |
| 4     | Typed tools and authorization                             | Planned                               |
| 5     | Durable worker, retries, idempotency and budgets          | Planned                               |
| 6     | Human approval and controlled mutations                   | Planned                               |
| 7     | Telemetry and trace UI                                    | Planned                               |
| 8     | Deterministic evaluation harness                          | Planned                               |
| 9     | Statistical comparison                                    | Planned                               |
| 10    | Sandboxed software engineering application                | Planned                               |
| 11    | MCP adapter through existing policy                       | Planned                               |
| 12    | AWS infrastructure with Terraform                         | Planned                               |
| 13    | Production CI/CD                                          | Planned                               |
| 14    | Temporary self-hosted inference and benchmarks            | Planned                               |
| 15    | Security hardening                                        | Planned                               |
| 16    | Public demo and portfolio release                         | Planned                               |

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
- **1C — Implemented, awaiting review:** durable model-invocation and tool-call
  requests; one-time success/failure outcomes; same-run model provenance; atomic
  outcome/event/step/checkpoint recording; migration and integration tests. See
  [ADR 0005](docs/adr/0005-invocation-records.md) and the
  [verification record](docs/operations/PHASE_1C.md).

## Recommended next slice

After Phase 1C review, begin Phase 2 with normalized model request/response and
structured-action contracts plus a deterministic scripted provider. Then add the
hosted adapter and an explicit opt-in live verification path within Phase 2.
All Phase 1 record types and acceptance tests are now implemented; actual model
calls, runtime execution, tool authorization and worker recovery remain later work.
