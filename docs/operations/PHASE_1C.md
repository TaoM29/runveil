# Phase 1C handoff

Date: 2026-09-26. Implemented and stopped for review. No commit or push.

## Implementation summary

Inspected the clean repository, root AGENTS instructions, charter, roadmap,
architecture, accepted ADRs, Phase 1A/1B implementation, migrations, tests and CI.
Recorded the architectural decision before implementation. The current phase
request takes precedence over the preserved charter's original Phase 0-only request.

Added durable `ModelInvocation` and `ToolCall` records with caller-supplied UUIDs,
immutable request data, request events and one-time success/failure outcomes.
Completion atomically records an outcome event, matching step, full checkpoint and
finalized record. Tool provenance can reference a succeeded model invocation in
the same run. Added migration 0003, typed domain snapshots, repository methods,
database guards, five PostgreSQL integration tests and one domain test. Updated
the existing schema round-trip test to include the new tables and constraints.

All Phase 1 record types and charter acceptance tests are implemented, awaiting
review. Provider calls, tool execution, authorization, worker recovery and retries
remain later work. No new package, dependency, HTTP route or web feature was added.

## Decisions

See [ADR 0005](../adr/0005-invocation-records.md) and
[persistence operations](PERSISTENCE.md) for contracts and examples.

- Persist request identity before future external work. REQUESTED means recorded
  intent; it does not mean dispatched, running, authorized or safe to retry.
- Reuse the run lock and required revision/sequence checks. Both request and
  completion writes require RUNNING. Caller-owned transactions still apply.
- Completion events reference record UUIDs; finalized records reference the
  completed step, whose details point back to the UUID. Checkpoint watermarks
  include the completion event. No intermediate step is misrepresented as complete.
- Separate model and tool records share only concrete lifecycle plumbing. Optional
  tool provenance must be same-run and succeeded, but does not authorize a tool.
- Success stores a JSON object; failure stores a bounded error code. Request/result
  data remain opaque, detached snapshots until later provider/tool contracts.
- Database guards enforce immutable requests, one-time outcomes and event/boundary
  correlation. Cancellation leaves unresolved requests visible and rejects late
  outcomes. Reconciliation is deliberately not invented in this persistence phase.

## Verification commands and results

Environment: macOS, Python 3.12.14, uv 0.12.19, Node 24.19.0,
PostgreSQL 17.9 in Docker. Verification used only a task-specific Compose project:

```sh
export PATH=/Users/taom/.nvm/versions/node/v24.19.0/bin:$PATH
POSTGRES_USER=runveil POSTGRES_PASSWORD=runveil-local-only POSTGRES_DB=runveil POSTGRES_PORT=55432 docker compose -p runveil-phase1c up -d --wait --wait-timeout 90
export DATABASE_URL='postgresql+psycopg://runveil:runveil-local-only@127.0.0.1:55432/runveil'
export RUNVEIL_TEST_DATABASE_URL='postgresql+psycopg://runveil:runveil-local-only@127.0.0.1:55432/postgres'
```

| Command                                              | Result                                                             |
| ---------------------------------------------------- | ------------------------------------------------------------------ |
| `uv sync --locked --all-packages`                    | Passed; no dependency changes                                      |
| `uv run ruff format --check .`                       | Passed; 48 files                                                   |
| `uv run ruff check .`                                | Passed                                                             |
| `uv run mypy`                                        | Passed; 30 source files                                            |
| `uv run pytest` with the test URL above              | 94 passed, no skips; includes 21 real PostgreSQL integration tests |
| `uv run alembic upgrade head`                        | Passed from empty task database                                    |
| `uv run alembic current`                             | `0003 (head)`                                                      |
| `uv run alembic check`                               | No new upgrade operations detected                                 |
| `uv run alembic downgrade 0002` then upgrade/check   | Passed on the task database only                                   |
| `npm ci`                                             | Passed; zero audit vulnerabilities                                 |
| `npm run format:check`                               | Passed                                                             |
| `npm run lint`                                       | Passed                                                             |
| `npm run typecheck`                                  | Passed                                                             |
| `npm test`                                           | One web test passed                                                |
| `npm run build`                                      | Production build passed                                            |
| `uv run python scripts/smoke.py` with database URL   | API/web boot, liveness, production page and readiness 200 passed   |
| `env -u DATABASE_URL uv run python scripts/smoke.py` | API/web boot, liveness, production page and readiness 503 passed   |
| `git diff --check`                                   | Passed                                                             |

The tests cover request/outcome persistence across connections, same-run model/tool
correlation, success and failure for both record types, detached nested JSON,
invalid outcome shapes, duplicate identities, immutable completed records,
request/finish rollback, uncommitted outcome invisibility, stale history,
one winner among competing completions, cancellation with unresolved intent,
direct-SQL integrity guards, populated Phase 1B upgrade/downgrade/re-upgrade,
empty-schema round-trip and metadata/constraint-name agreement.

Initial checks caught SQL formatting and two typing issues in shared snapshot/query
handling; corrected before the final passing checks. Completion state is detached
before any database await, alongside request/result data. Existing npm notices
about ESLint 9 deprecation and install-script policy remain; no dependencies were
changed. Hosted GitHub Actions was not run. Existing CI already discovers the new
tests and migrations, so no workflow change was needed. No paid/live provider calls
were made.

Confirmed zero remaining `runveil_test_*` databases. Removed only the task-created
`runveil-phase1c` container, network and volume using the same Compose variables and
`docker compose -p runveil-phase1c down --volumes`. Existing services, data and
`.env` were preserved. Smoke servers stopped themselves.

## Files created

- `docs/adr/0005-invocation-records.md`
- `docs/operations/PHASE_1C.md`
- `packages/agent_core/src/runveil_core/invocations.py`
- `packages/agent_core/tests/test_invocation_domain.py`
- `packages/persistence/migrations/versions/0003_invocation_records.py`
- `packages/persistence/src/runveil_persistence/invocations.py`
- `packages/persistence/tests/test_invocations.py`

## Files modified

- `ARCHITECTURE.md`
- `README.md`
- `ROADMAP.md`
- `docs/operations/PERSISTENCE.md`
- `packages/persistence/src/runveil_persistence/history.py`
- `packages/persistence/src/runveil_persistence/models.py`
- `packages/persistence/tests/test_persistence.py`

## Remaining concerns and recommended next slice

Request/result/checkpoint JSON is still opaque selected content, with no payload
limit, retention policy or automatic redaction. Never store credentials or hidden
reasoning. Recorded timestamps describe persistence boundaries, not external call
latency. Runtime-specific schemas and provider normalization remain unimplemented.

Database guards are integrity rules, not authorization or protection against a
privileged database owner. UUID identity does not deliver external idempotency or
exactly-once execution. Pending records after cancellation or uncertain external
outcomes require future reconciliation; no retry policy is implied. Multi-query
reads remain READ COMMITTED; future callers must check revision and event position.

Downgrade to 0002 removes invocation/tool records while leaving history/checkpoints,
including unresolved UUID references in JSON. Re-upgrade cannot recreate deleted
records. Production roles, deployment, public-name clearance and license remain
open.

After review, begin **Phase 2 with normalized model contracts, structured actions
and a scripted provider**, followed by a hosted adapter and opt-in live verification
within that phase. Keep the execution loop and tool execution in their planned
phases.
