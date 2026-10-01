# Phase 5B handoff

Date: 2026-09-27. Implementation complete; stopped for review. No commit or push.

## Scope and decisions

Inspected the clean repository, root instructions, charter, architecture, roadmap,
accepted persistence/runtime/worker ADRs, completed Phase 5A implementation and
handoff, README and CI. The user's request authorizes this next Phase 5 slice;
Phase 5 as a whole remains incomplete. Preserved the historical charter verbatim.

Recorded [ADR 0012](../adr/0012-persisted-model-retries.md) before implementation.
Implemented bounded persisted model retries for a new offline profile:

- `fixture-retry-v1` deliberately produces two known pre-response rate-limit
  failures, then completes the existing fixture workflow. Response selection uses
  durable retry counts; no in-memory script index must survive restart.
- Configuration version 3 pins a run-wide retry limit and base delay. Checkpoint
  version 3 retains scheduled count and failed source. Version-2 configurations
  and the default `fixture-v1` profile retain their behavior.
- Core requires an explicit rate-limit failure, pinned capacity, remaining steps
  and a trusted operator retry grant. The grant is rechecked before resumed retry
  dispatch. Timeouts, unknown/unavailable failures, invalid model output, tool
  failures and uncertain dispatch are not retried.
- Scheduling atomically commits the failed invocation, checkpoint, schedule event,
  RETRYING lifecycle transition, next eligibility and lease release. PostgreSQL
  polling and resumption both check the database-clock deadline. There is no
  worker-held sleep or heartbeat during backoff.
- Resumption verifies history, provenance and counts, then atomically transitions
  to RUNNING and checkpoints the continuation. Every new attempt uses a distinct
  invocation ID; its event links the failed predecessor and its request must match.
- Retry count never resets after successful operations. Every attempt consumes a
  step. Retry exhaustion retains the provider failure; scheduling cannot exceed
  either the retry limit or remaining step capacity.
- Migration 0005 adds only job eligibility. Existing enrollment, run/configuration
  records and history remain intact. No dependency, manifest or lockfile changes.

Policy bounds are 0–3 retries and a 1–60 second base delay, doubled per scheduled
retry (maximum 240 seconds). The demo uses two retries, one-/two-second delays and
five invocation steps. This is not a hosted-provider safe-replay guarantee, a
broker integration or a general-purpose retry framework.

## Files created

- `docs/adr/0012-persisted-model-retries.md`
- `docs/operations/PHASE_5B.md`
- `packages/agent_core/tests/test_runtime_policy.py`
- `packages/persistence/migrations/versions/0005_retry_eligibility.py`
- `packages/persistence/tests/test_retries.py`

## Files modified

- `apps/worker/src/runveil_worker/__main__.py`
- `apps/worker/src/runveil_worker/worker.py`
- `packages/agent_core/src/runveil_core/runtime.py`
- `packages/persistence/src/runveil_persistence/execution.py`
- `packages/persistence/src/runveil_persistence/invocations.py`
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
Used a disposable Compose project; existing services and `.env` were preserved:

```sh
export PATH="$HOME/.nvm/versions/node/v24.19.0/bin:$PATH"
POSTGRES_USER=runveil POSTGRES_PASSWORD=runveil-local-only POSTGRES_DB=runveil POSTGRES_PORT=55435 docker compose -p runveil-phase5b up -d --wait --wait-timeout 90
export DATABASE_URL='postgresql+psycopg://runveil:runveil-local-only@127.0.0.1:55435/runveil'
export RUNVEIL_TEST_DATABASE_URL='postgresql+psycopg://runveil:runveil-local-only@127.0.0.1:55435/postgres'
```

| Command                                                                                                                                                                                            | Result                                                                                              |
| -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| `uv sync --locked --all-packages`                                                                                                                                                                  | Passed; no dependency changes                                                                       |
| `uv run ruff format --check .`                                                                                                                                                                     | Passed                                                                                              |
| `uv run ruff check .`                                                                                                                                                                              | Passed                                                                                              |
| `uv run mypy`                                                                                                                                                                                      | Passed, 57 source files                                                                             |
| `uv run pytest` with test database URL                                                                                                                                                             | 192 passed, no skips; 70 PostgreSQL integration cases                                               |
| `uv run pytest packages/persistence/tests/test_retries.py packages/persistence/tests/test_worker.py packages/persistence/tests/test_execution.py packages/agent_core/tests/test_runtime_policy.py` | 49 passed after the resumed operator-grant refinement                                               |
| `uv run alembic upgrade head`                                                                                                                                                                      | Passed on empty task database                                                                       |
| `uv run alembic check`                                                                                                                                                                             | No new upgrade operations detected                                                                  |
| `uv run python -m runveil_worker submit --profile fixture-retry-v1`                                                                                                                                | Created one enrolled retry-profile run                                                              |
| `uv run python -m runveil_worker work --once --profile fixture-retry-v1` across separate processes                                                                                                 | RETRYING at steps/retries 1/1 and 2/2, then SUCCEEDED at 5/2; final delivery found no eligible work |
| `uv run python -m runveil_worker submit` and `work --once`                                                                                                                                         | Original profile SUCCEEDED at three steps, zero retries                                             |
| `uv run python scripts/runtime_demo.py`                                                                                                                                                            | Repository demonstration SUCCEEDED at five steps                                                    |
| `npm ci`                                                                                                                                                                                           | Passed; zero audit vulnerabilities                                                                  |
| `npm run format:check`                                                                                                                                                                             | Passed                                                                                              |
| `npm run lint`                                                                                                                                                                                     | Passed                                                                                              |
| `npm run typecheck`                                                                                                                                                                                | Passed                                                                                              |
| `npm test`                                                                                                                                                                                         | One web test passed                                                                                 |
| `npm run build`                                                                                                                                                                                    | Production build passed                                                                             |
| `uv run python scripts/smoke.py`                                                                                                                                                                   | API/web health, page and readiness 200 passed                                                       |
| `env -u DATABASE_URL uv run python scripts/smoke.py`                                                                                                                                               | API/web health, page and readiness 503 passed                                                       |
| `git diff --check`                                                                                                                                                                                 | Passed                                                                                              |

One unit test checks version gating and bounded policy/backoff. Four focused
PostgreSQL test functions (11 cases) cover persisted exponential backoff, fresh
engine/process-state recovery, attempt links and unchanged requests, retry/step
limits (including a limit reached after a retry), non-retryable errors, operator
grant denial/revocation, transaction rollback, stale-owner rejection, due claim
competition, cancellation, early direct resume refusal, changed-request refusal,
clean resume recovery and interrupted retry intent. Tests control the scheduling
clock seam rather than sleeping. The existing migration test now verifies both a
populated pre-worker database and a pre-eligibility job through upgrade, metadata,
constraint comparison, downgrade and re-upgrade.

Initial checks caught integer exponent type inference and formatting/unused-loop
issues; corrected before final checks. Review added operator-grant revalidation
for already-scheduled retries, then reran all affected runtime/worker tests. npm
emitted existing ESLint deprecation and install-script notices. No live/paid model
calls, production deployment, hosted Linux CI or SIGKILL test is claimed.

Confirmed zero remaining randomly named integration databases. Removed only the
`runveil-phase5b` container, network and volume, including disposable demo records.
Existing services and `.env` were preserved. Smoke checks stopped their processes.

## Remaining concerns and next slice

The retry-enabled profile is intentionally offline. A hosted rate-limit error is
not sufficient evidence of safe external replay; provider idempotency/safety policy
is still required. Unknown outcomes remain terminal. Tool retries, jitter, general
repair strategies, poison-job quarantine and production scheduling are deferred.
Ownership fences protect database writes, not execution in a paused old process.
Low-level repositories remain trusted administrative APIs.

Review Phase 5B, then implement a **durable elapsed-time budget** spanning execution,
retry waits and worker restarts: persist the deadline, prevent new dispatch after
expiry, and verify interaction with claims and cancellation. Token/cost accounting
needs explicit unknown-usage semantics in a subsequent slice. Repository recovery
still needs workspace/implementation identity. Mutations, approvals and MCP remain
in their planned phases.
