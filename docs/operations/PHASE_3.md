# Phase 3 handoff

Date: 2026-09-26. Implementation complete; stopped for review. No commit or push.

## Implementation and decisions

Inspected clean repository state, root instructions, charter, architecture, roadmap,
accepted ADRs, existing model/provider and persistence code/tests, previous handoff,
README and CI. The charter's historical opening “Phase 0 only” instruction and the
previous handoff's live-gate sequencing are superseded for this slice by the user's
explicit Phase 3 request. Hosted live acceptance was pending at implementation
time, not waived; it has since [passed](PHASE_2B.md#subsequent-hosted-live-acceptance--complete).
Recorded [ADR 0008](../adr/0008-minimal-runtime.md) before implementation.

Implemented the planned deterministic task → model → fixed read-only fixture tool
→ model → finish loop. Core owns context assembly, structured actions, model
execution deadline, shared model/tool invocation step bound and final/error state.
A small storage protocol keeps core independent of SQLAlchemy. The PostgreSQL
adapter uses existing repositories and short committed transactions; no migration,
package or dependency changes were necessary.

The run's immutable agent version pins validated runtime configuration. Start
persists the task/conversation before work. Requests commit before dispatch;
outcomes create correlated steps/checkpoints. Terminal outcome and lifecycle
transition commit together. Provider errors and invalid actions fail safely;
invalid tool arguments fail the tool record. Unknown provider exceptions produce
only a fixed code. Stale decisions and task cancellation propagate without retries.

Only `fixture.info` is available, accepting `{}` and returning fixed public
metadata. There is no filesystem, shell, network, arbitrary callback or production
tool authorization surface. Phase 4 will introduce typed tools and policy. No
worker, recovery, resume, lease, retry, approval or HTTP execution endpoint was added.

The offline demo creates a new agent/version/run, executes the same loop and reads
back its final state. See [runtime operations](RUNTIME.md) for usage and boundaries.
Five integration test functions (16 parametrized cases) verify the complete run and
pinned version, provider context and provenance, restored state through a new engine,
last-step success, bounds before model/tool dispatch, safe failures, committed intent,
unlocked provider waits, competing execution/history, task/lifecycle cancellation,
rejected late results and invalid-start rollback.

## Files created

- `packages/agent_core/src/runveil_core/runtime.py`
- `packages/persistence/src/runveil_persistence/execution.py`
- `packages/persistence/tests/test_execution.py`
- `scripts/runtime_demo.py`
- `docs/adr/0008-minimal-runtime.md`
- `docs/operations/RUNTIME.md`
- `docs/operations/PHASE_3.md`

## Files modified

- `README.md`
- `ARCHITECTURE.md`
- `ROADMAP.md`

## Verification

Environment: macOS, Python 3.12.14, uv 0.12.19, Node 24.19.0, Docker PostgreSQL.
Used a separate task-owned Compose project and port; preserved existing services
and `.env`:

```sh
export PATH="$HOME/.nvm/versions/node/v24.19.0/bin:$PATH"
POSTGRES_USER=runveil POSTGRES_PASSWORD=runveil-local-only POSTGRES_DB=runveil POSTGRES_PORT=55433 docker compose -p runveil-phase3 up -d --wait --wait-timeout 90
export DATABASE_URL='postgresql+psycopg://runveil:runveil-local-only@127.0.0.1:55433/runveil'
export RUNVEIL_TEST_DATABASE_URL='postgresql+psycopg://runveil:runveil-local-only@127.0.0.1:55433/postgres'
```

| Command                                                      | Result                                                          |
| ------------------------------------------------------------ | --------------------------------------------------------------- |
| `uv sync --locked --all-packages`                            | Passed; no dependency changes                                   |
| `uv run ruff format --check .`                               | Passed                                                          |
| `uv run ruff check .`                                        | Passed                                                          |
| `uv run mypy`                                                | Passed; 42 source files                                         |
| `uv run alembic upgrade head`                                | Passed on empty task database                                   |
| `uv run alembic check`                                       | No new upgrade operations detected                              |
| `uv run pytest`                                              | 140 passed, including 38 PostgreSQL integration cases; no skips |
| `uv run pytest packages/persistence/tests/test_execution.py` | 16 passed; rerun after final pinned-version assertion           |
| `npm ci`                                                     | Passed; zero audit vulnerabilities                              |
| `npm run format:check`                                       | Passed                                                          |
| `npm run lint`                                               | Passed                                                          |
| `npm run typecheck`                                          | Passed                                                          |
| `npm test`                                                   | One web test passed                                             |
| `npm run build`                                              | Production build passed                                         |
| `uv run python scripts/runtime_demo.py`                      | SUCCEEDED; three consumed steps; restored result verified       |
| `uv run python scripts/smoke.py`                             | API/web health, production page, readiness 200 passed           |
| `env -u DATABASE_URL uv run python scripts/smoke.py`         | API/web health, production page, readiness 503 passed           |
| Compose config and `SELECT 1` with the variables above       | Passed                                                          |
| `git diff --check`                                           | Passed                                                          |

Initial type checking caught an incorrect repository keyword and a test union
narrowing error; both were fixed before the successful checks. npm emitted existing
ESLint deprecation and install-script notices; no frontend changes were made.
No hosted CI or live/paid model call was run. The demo used only scripted responses.

Confirmed zero remaining randomly named integration databases. Removed only the
task-created `runveil-phase3` container, network and volume after verification;
this also removes the disposable demo record. Existing volumes and `.env` were
preserved. The smoke scripts stopped their own application processes.

## Remaining concerns and next slice

Hosted Phase 2 acceptance is now complete through a separately reported live
invocation; see [the evidence](PHASE_2B.md#subsequent-hosted-live-acceptance--complete).
The offline results in this handoff remain distinct from that hosted evidence.

A checkpoint is reconstruction evidence, not a recovery mechanism. Interruption
can leave a RUNNING run with REQUESTED work; this implementation refuses resume.
A cancelled/stale remote request may still have executed or been billed. Storage
errors propagate rather than being mislabeled as provider failures or retried.
Worker claims, reconciliation and durable recovery belong to Phase 5.

The step cap is not a token, cost or total-duration budget. Context is bounded by
step/message contracts but has no compaction; valid task/model/tool content is
persisted and must be selected safely by callers. The fixed fixture is deliberately
not a production tool authorization or sandbox boundary.

Recommended next slice after review: **Phase 4**, a small typed tool registry with
strict input/output validation and explicit authorization around native read-only
tools. Keep mutation approval, worker recovery and MCP in their planned phases.
