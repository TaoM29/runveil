# Phase 5A handoff

Date: 2026-09-27. Implementation complete; stopped for review. No commit or push.

## Scope and decisions

Inspected the clean repository, root instructions, charter, architecture, roadmap,
accepted ADRs, completed runtime/tool/persistence implementation and tests, Phase
4B handoff, README and CI. The user's Phase 5 request authorizes continuation past
the Phase 4B review stop. The charter's historical “Phase 0 only” instruction is
superseded by this request; the original charter is preserved.

Selected the roadmap's first durable worker slice. Phase 5 is not complete.
Recorded [ADR 0011](../adr/0011-durable-fixture-worker.md) before implementation.

- Added a real worker app and fixed `fixture-v1` profile with a deterministic,
  context-driven offline provider and the existing fixture tool/policy.
- PostgreSQL enrollment stores the task/profile and uses the run ID as delivery
  identity. Submission creates the version, run and job in one transaction.
  Repeated identical enrollment is harmless; conflicting enrollment is rejected.
- Polling uses run-row locks with `SKIP LOCKED`, a random claim token and a
  database-clock lease. All execution-store boundaries check ownership and expiry
  under the run lock and renew in the same transaction. Unclaimed stores refuse
  enrolled runs. Expired/superseded outcomes and lifecycle-stale results cannot commit.
- Checkpoint version 2 retains the next tool action and model provenance. Resume
  validates lifecycle revision, history tail, invocation count and provenance.
  Committed outcomes are not repeated, and consumed steps survive restart.
- Unresolved model/tool intent becomes an atomic `execution_interrupted` failed
  outcome/checkpoint/terminal transition. It is never replayed, even when dispatch
  may not have happened. Unknown/inconsistent recovery state fails closed.
- Migration 0004 adds immutable job enrollment plus mutable lease fields, without
  rewriting or enrolling existing runs. Old runtime snapshots remain inspectable.
- No external dependencies were added or upgraded; the lockfile adds only the
  worker workspace package. No API/UI endpoints, hosted calls or repository replay.

The PostgreSQL queue avoids adding a broker/outbox before it is needed. The fixed
660-second lease is renewed only at runtime boundaries, exceeding the maximum
600-second provider timeout; no heartbeat machinery is necessary for this offline
profile. Process death may delay recovery until lease expiry. This is ownership
and conservative recovery, not exactly-once external execution or automatic retry.

## Files created

- `apps/worker/pyproject.toml`
- `apps/worker/src/runveil_worker/__init__.py`
- `apps/worker/src/runveil_worker/__main__.py`
- `apps/worker/src/runveil_worker/worker.py`
- `apps/worker/src/runveil_worker/py.typed`
- `packages/persistence/src/runveil_persistence/jobs.py`
- `packages/persistence/migrations/versions/0004_worker_jobs.py`
- `packages/persistence/tests/test_worker.py`
- `docs/adr/0011-durable-fixture-worker.md`
- `docs/operations/WORKER.md`
- `docs/operations/PHASE_5A.md`

## Files modified

- `packages/agent_core/src/runveil_core/runtime.py`
- `packages/persistence/src/runveil_persistence/execution.py`
- `packages/persistence/src/runveil_persistence/models.py`
- `packages/persistence/tests/test_persistence.py`
- `pyproject.toml`
- `uv.lock`
- `README.md`
- `ARCHITECTURE.md`
- `ROADMAP.md`
- `docs/operations/RUNTIME.md`

## Verification

Environment: macOS, Python 3.12.14, uv 0.12.19, Node 24.19.0, Docker PostgreSQL 17.
Used an isolated Compose project, preserving existing services and `.env`:

```sh
export PATH="$HOME/.nvm/versions/node/v24.19.0/bin:$PATH"
POSTGRES_USER=runveil POSTGRES_PASSWORD=runveil-local-only POSTGRES_DB=runveil POSTGRES_PORT=55435 docker compose -p runveil-phase5a up -d --wait --wait-timeout 90
export DATABASE_URL='postgresql+psycopg://runveil:runveil-local-only@127.0.0.1:55435/runveil'
export RUNVEIL_TEST_DATABASE_URL='postgresql+psycopg://runveil:runveil-local-only@127.0.0.1:55435/postgres'
```

| Command                                                                                                  | Result                                                      |
| -------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------- |
| `uv lock`                                                                                                | Added only the worker workspace package                     |
| `uv sync --locked --all-packages`                                                                        | Passed                                                      |
| `uv run ruff format --check .`                                                                           | Passed                                                      |
| `uv run ruff check .`                                                                                    | Passed                                                      |
| `uv run mypy`                                                                                            | Passed, 54 source files                                     |
| `uv run pytest` with test database URL                                                                   | 180 passed, no skips; 59 PostgreSQL integration cases       |
| `uv run pytest packages/persistence/tests/test_worker.py packages/persistence/tests/test_persistence.py` | 21 passed after migration/immutability refinements          |
| `uv run alembic upgrade head`                                                                            | Passed on empty task database                               |
| `uv run alembic check`                                                                                   | No new upgrade operations detected                          |
| `uv run python -m runveil_worker submit`                                                                 | Created one enrolled run                                    |
| `uv run python -m runveil_worker work --once`                                                            | SUCCEEDED, three consumed steps                             |
| Same worker command again                                                                                | `no_eligible_work`; terminal run not repeated               |
| `uv run python scripts/runtime_demo.py`                                                                  | SUCCEEDED, five steps; repository demonstration still works |
| `npm ci`                                                                                                 | Passed; zero audit vulnerabilities                          |
| `npm run format:check`                                                                                   | Passed                                                      |
| `npm run lint`                                                                                           | Passed                                                      |
| `npm run typecheck`                                                                                      | Passed                                                      |
| `npm test`                                                                                               | One web test passed                                         |
| `npm run build`                                                                                          | Production build passed                                     |
| `uv run python scripts/smoke.py`                                                                         | API/web health, page and readiness 200 passed               |
| `env -u DATABASE_URL uv run python scripts/smoke.py`                                                     | API/web health, page and readiness 503 passed               |
| `git diff --check`                                                                                       | Passed                                                      |

Four focused worker test functions (11 cases) cover six committed crash boundaries,
process-state recreation through a fresh database engine, duplicate delivery,
competing claims, expiry before takeover, replacement-token rejection at every
write boundary, cancellation, enrollment identity/immutability, profile mismatch,
and unsupported/inconsistent checkpoints. The existing migration test now also
upgrades a populated 0003 database without adopting existing runs and verifies
metadata, constraints, downgrade and re-upgrade. Existing runtime tests continue
to cover step limits, authorization, deadlines, safe failures and repository bounds.

Initial formatting/type checks caught long lines and SQLAlchemy union inference;
corrected before passing checks. npm emitted existing ESLint deprecation and
install-script notices. No live/paid provider call, public deployment or hosted
Linux CI run was performed. Crash tests interrupt at committed boundaries and
recreate execution objects; they do not claim SIGKILL or real provider replay tests.

Confirmed zero remaining randomly named integration databases. Removed only the
`runveil-phase5a` container, network and volume, including its disposable demo
records. Existing services and `.env` were preserved; smoke processes stopped.

## Remaining concerns and next slice

Only the fixed offline profile is worker-enabled. Recovery refuses old runtime
snapshots, arbitrary repository bindings and unrecognized profiles. Profile IDs
must change with implementation semantics. An invalid job stops the worker for
investigation; no quarantine/supervisor or automatic repair is implemented.
Leases fence writes, not execution in a paused old process. Low-level persistence
repositories remain trusted administrative APIs. Database roles and production
privilege separation remain future hardening work.

Review Phase 5A, then implement **bounded persisted model retry attempts** for a
versioned offline worker profile: retry classification, attempt counts, next
eligibility time/backoff and durable step accounting. Keep uncertain dispatch
conservative until provider idempotency is explicitly supported. Token/cost/time
budgets, broader worker profiles and workspace identity remain subsequent Phase 5
slices. Mutations, approvals and MCP remain in their planned phases.
