# Roadmap

The [original charter](docs/PROJECT_PLAN.md) is the source of truth. Each phase must
be independently reviewed before the next begins. No automatic continuation,
commit or push is authorized.

| Phase | Scope                                                     | Status                                  |
| ----- | --------------------------------------------------------- | --------------------------------------- |
| 0     | Charter, workspaces, health, quality tooling, Compose, CI | Implemented; see verification record    |
| 1     | Domain model, immutable versions, persistence, migrations | Phase 1A implemented; remainder pending |
| 2     | Provider protocol, scripted and hosted providers          | Planned                                 |
| 3     | Minimal persisted execution loop                          | Planned                                 |
| 4     | Typed tools and authorization                             | Planned                                 |
| 5     | Durable worker, retries, idempotency and budgets          | Planned                                 |
| 6     | Human approval and controlled mutations                   | Planned                                 |
| 7     | Telemetry and trace UI                                    | Planned                                 |
| 8     | Deterministic evaluation harness                          | Planned                                 |
| 9     | Statistical comparison                                    | Planned                                 |
| 10    | Sandboxed software engineering application                | Planned                                 |
| 11    | MCP adapter through existing policy                       | Planned                                 |
| 12    | AWS infrastructure with Terraform                         | Planned                                 |
| 13    | Production CI/CD                                          | Planned                                 |
| 14    | Temporary self-hosted inference and benchmarks            | Planned                                 |
| 15    | Security hardening                                        | Planned                                 |
| 16    | Public demo and portfolio release                         | Planned                                 |

## Phase 1 review gates

- **1A — Implemented, awaiting review:** agent definitions; versions immutable from
  creation; persisted runs; validated lifecycle transitions and timestamps; expected
  revisions for concurrency; initial PostgreSQL migration; database readiness;
  deterministic unit and PostgreSQL integration tests. See the
  [verification record](docs/operations/PHASE_1A.md) and
  [ADR 0003](docs/adr/0003-phase-1a-persistence.md).
- **1B — Next, after review:** ordered run steps/events and checkpoint persistence,
  with atomic ordering/restore tests. Add invocation/tool-call records within the
  remaining Phase 1 scope as needed; no model calls or execution loop.

## Recommended next slice

After Phase 1A review, design the transaction boundary for ordered execution events
and checkpoints, then implement persistence and tests proving event order and
checkpoint restoration. Phase 1 is incomplete until all its charter acceptance
criteria pass. Provider and runtime work must wait.
