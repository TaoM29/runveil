# Phase 5C handoff

Date: 2026-09-27. Implementation complete; stopped for review. No commit or push.

## Scope and decisions

Inspected the clean repository, root instructions, charter, architecture, roadmap,
accepted runtime/worker/retry ADRs, completed Phase 5B implementation and handoff,
README and CI. The current request authorizes this next Phase 5 slice. The original
charter is preserved; its historical Phase 0-only instruction is superseded by
the user's continuation. Phase 5 as a whole remains incomplete.

Recorded [ADR 0013](../adr/0013-durable-elapsed-budget.md) before implementation.
Implemented the planned durable elapsed-time budget:

- Configuration/checkpoint version 4 requires an integer elapsed limit of 1–86400
  seconds. Existing version-2/3 configurations and profiles keep their behavior.
- Migration 0006 adds an optional worker-job deadline and a trigger preventing
  changes to an assigned deadline. Start initializes it atomically from the first
  run start timestamp and pinned limit; recovery verifies that relationship.
- Initial queue time is excluded. Execution, retry backoff and process downtime
  after first start all count; restart never resets the deadline.
- A shared execution-store transaction boundary enforces ownership, revision/
  history and elapsed checks before request, outcome, schedule and step-limit
  writes. Core also checks after intent before dispatch and after each operation.
- Cooperative model/tool timeouts shrink to the remaining budget without changing
  persisted model request identity. Expiry never becomes a retryable failure.
- Expiry atomically records `elapsed_time_exceeded`, a failed checkpoint,
  `budget.exceeded` and FAILED. Pending invocations receive one failed outcome and
  consume one step; no new intent consumes no step. Late results are discarded.
  Only after commit does a control exception return the persisted state to core.
- Expired backoff is claimable before retry eligibility, but active leases are
  never stolen. Cancellation/stale ownership is checked before budget finalization.
- Added the opt-in offline `fixture-budget-v1` profile: the existing two-failure
  retry fixture with a 30-second elapsed budget. No hosted calls, repository
  replay, new packages, dependencies, manifests or lockfile changes.

The deadline uses database wall-clock time. It is an admission boundary with
cooperative cancellation, not a hard real-time sandbox. A process pause after a
check can delay dispatch; native blocking code and already-sent external requests
cannot be forcibly stopped. A crashed owner can delay cleanup until lease expiry.
Retry continuation and subsequent budget finalization are separate recoverable
transactions; expiry cleanup may pass through RUNNING without external dispatch.

## Files created

- `docs/adr/0013-durable-elapsed-budget.md`
- `docs/operations/PHASE_5C.md`
- `packages/persistence/migrations/versions/0006_elapsed_deadline.py`
- `packages/persistence/tests/test_elapsed_budget.py`

## Files modified

- `apps/worker/src/runveil_worker/__main__.py`
- `apps/worker/src/runveil_worker/worker.py`
- `packages/agent_core/src/runveil_core/runtime.py`
- `packages/agent_core/tests/test_runtime_policy.py`
- `packages/persistence/src/runveil_persistence/execution.py`
- `packages/persistence/src/runveil_persistence/jobs.py`
- `packages/persistence/src/runveil_persistence/models.py`
- `packages/persistence/tests/test_persistence.py`
- `README.md`
- `ARCHITECTURE.md`
- `ROADMAP.md`
- `docs/operations/RUNTIME.md`
- `docs/operations/WORKER.md`
- `docs/operations/PERSISTENCE.md`

## Verification

Environment: macOS, Python 3.12.14, uv 0.12.19, Node 24.19.0, Docker PostgreSQL 17.
Used a disposable Compose project, preserving existing services and `.env`:

```sh
export PATH="$HOME/.nvm/versions/node/v24.19.0/bin:$PATH"
POSTGRES_USER=runveil POSTGRES_PASSWORD=runveil-local-only POSTGRES_DB=runveil POSTGRES_PORT=55435 docker compose -p runveil-phase5c up -d --wait --wait-timeout 90
export DATABASE_URL='postgresql+psycopg://runveil:runveil-local-only@127.0.0.1:55435/runveil'
export RUNVEIL_TEST_DATABASE_URL='postgresql+psycopg://runveil:runveil-local-only@127.0.0.1:55435/postgres'
```

| Command                                                                                             | Result                                                                                              |
| --------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| `uv sync --locked --all-packages`                                                                   | Passed; no dependency changes                                                                       |
| `uv run ruff format --check .`                                                                      | Passed                                                                                              |
| `uv run ruff check .`                                                                               | Passed                                                                                              |
| `uv run mypy`                                                                                       | Passed, 59 source files                                                                             |
| `uv run pytest` with test database URL                                                              | 204 passed, no skips; 81 PostgreSQL integration cases                                               |
| `uv run alembic upgrade head`                                                                       | Passed on empty task database                                                                       |
| `uv run alembic check`                                                                              | No new upgrade operations detected                                                                  |
| `uv run python -m runveil_worker submit --profile fixture-budget-v1`                                | Created one enrolled budget-profile run                                                             |
| `uv run python -m runveil_worker work --once --profile fixture-budget-v1` across separate processes | RETRYING at steps/retries 1/1 and 2/2, then SUCCEEDED at 5/2; final delivery found no eligible work |
| `uv run python -m runveil_worker submit` and `work --once`                                          | Original profile SUCCEEDED at three steps, zero retries                                             |
| `uv run python scripts/runtime_demo.py`                                                             | Repository demonstration SUCCEEDED at five steps                                                    |
| `npm ci`                                                                                            | Passed; zero audit vulnerabilities                                                                  |
| `npm run format:check`                                                                              | Passed                                                                                              |
| `npm run lint`                                                                                      | Passed                                                                                              |
| `npm run typecheck`                                                                                 | Passed                                                                                              |
| `npm test`                                                                                          | One web test passed                                                                                 |
| `npm run build`                                                                                     | Production build passed                                                                             |
| `uv run python scripts/smoke.py`                                                                    | API/web health, page and readiness 200 passed                                                       |
| `env -u DATABASE_URL uv run python scripts/smoke.py`                                                | API/web health, page and readiness 503 passed                                                       |
| `git diff --check`                                                                                  | Passed                                                                                              |

One new unit test verifies explicit configuration-version gating, strict integer
input and limit bounds. Four PostgreSQL test functions (11 cases) cover deadline
initialization/immutability, retries with fresh database engines, expiry before
retry eligibility, cancellation, request/dispatch boundaries, late model/tool
results, cooperative timeout cancellation, atomic expiry rollback and stale-owner
rejection. Expiry tests control the scheduling clock; timeout cases await a blocked
operation under a short deadline rather than sleeping. Existing worker tests still
exercise restart at committed boundaries and uncertain-intent failure.

The populated migration test now also verifies a pre-deadline job through upgrade,
unchanged eligibility/enrollment, null legacy deadline, metadata/constraint
comparison, downgrade and re-upgrade. The complete suite passed after correcting
initial test fixture field names and respecting the fixture output's literal type.
npm emitted existing ESLint deprecation and install-script notices. No live/paid
provider calls, public deployment, hosted Linux CI or SIGKILL test is claimed.

Confirmed zero remaining randomly named integration databases. Removed only the
`runveil-phase5c` container, network and volume, including disposable demo records.
Existing services and `.env` were preserved. Smoke checks stopped their processes.

## Remaining concerns and next slice

Token and cost budgets remain unimplemented. Discarded late results and uncertain
calls will require explicit unknown-usage accounting, not fabricated zero usage.
There is no background deadline sweeper or live-lease takeover. Wall-clock changes
follow PostgreSQL's clock; local async timeouts bound only cooperative waiting.
Low-level repositories remain trusted administrative APIs, and production database
privilege separation is still future hardening work.

Review Phase 5C, then implement **durable token accounting and a bounded token
budget**, with explicit unknown-usage handling for failed/uncertain attempts and
persistence across retries/restarts. Cost budgets need pinned pricing semantics in
a later slice. Repository recovery still requires workspace/implementation identity;
hosted retry requires provider idempotency/safety policy. Mutations, approvals and
MCP remain in their planned phases.
