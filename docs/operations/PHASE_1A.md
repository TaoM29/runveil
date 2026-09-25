# Phase 1A handoff

Date: 2026-09-25. Implemented and stopped for review. No commit or push.

## Implementation summary

Inspected the clean Runveil checkout, root AGENTS instructions, original charter,
architecture, roadmap, ADRs, configuration and existing implementation. The roadmap's
next slice was immutable versions and persisted run lifecycle. The user's Phase 1A
request supersedes the preserved charter's original Phase 0-only instruction.

Added framework-independent agent definitions, immutable configuration snapshots
and run lifecycle rules; concrete async PostgreSQL repositories; migration 0001;
database guards; isolated database integration tests; API connectivity readiness;
and CI migration/integration verification. Updated setup, architecture, roadmap,
contribution guidance and persistence operations. The original charter is unchanged.

No event history, steps, checkpoints, model invocations, tool calls, worker,
execution loop, domain HTTP routes or UI features were implemented.

## Architectural decisions

See [ADR 0003](../adr/0003-phase-1a-persistence.md).

- Core domain code is independent of FastAPI/SQLAlchemy; persistence is a shared
  adapter package available to the API and a future worker.
- Versions are immutable immediately on creation, including at the database layer.
  Their opaque JSON configuration is copied on access; changes create a new version.
- Callers own transactions. Parent locks serialize version numbers; run locks plus
  required expected revisions prevent stale transition decisions.
- Domain validation and PostgreSQL guards enforce the lifecycle. Store first-start,
  most-recent-transition and terminal timestamps; full history waits for Phase 1B.
- Readiness is a bounded connectivity check, separate from liveness and migrations.
- Tests create/drop only randomly named temporary databases, using an explicit
  administrative test URL. No SQLite substitute or developer-database resets.

## Verification commands and results

Environment: macOS, Python 3.12.14, uv 0.12.19, Node 24.19.0,
PostgreSQL 17.9 in Docker. Node 24's executable directory was added to PATH.
An existing database occupied the usual local setup, so verification used a separate
Compose project and port. Existing containers, volumes and `.env` were preserved.

The dedicated test dependency was started with:

```sh
POSTGRES_USER=runveil POSTGRES_PASSWORD=runveil-local-only POSTGRES_DB=runveil POSTGRES_PORT=55432 docker compose -p runveil-phase1a up -d --wait --wait-timeout 90
```

Database checks used these local-only test credentials:

```sh
export DATABASE_URL='postgresql+psycopg://runveil:runveil-local-only@127.0.0.1:55432/runveil'
export RUNVEIL_TEST_DATABASE_URL='postgresql+psycopg://runveil:runveil-local-only@127.0.0.1:55432/postgres'
```

| Command                                                           | Result                                                                          |
| ----------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| `uv sync --locked --all-packages`                                 | Passed; manifests and lock agree                                                |
| `uv run ruff format --check .`                                    | Passed                                                                          |
| `uv run ruff check .`                                             | Passed                                                                          |
| `uv run mypy`                                                     | Passed; 20 source files                                                         |
| `uv run pytest` with test URL above                               | 82 passed, no skips                                                             |
| `uv run alembic upgrade head`                                     | Passed from empty task database                                                 |
| `uv run alembic current`                                          | `0001 (head)`                                                                   |
| `uv run alembic check`                                            | No new upgrade operations detected                                              |
| `uv run alembic downgrade base` followed by upgrade/current/check | Passed on the disposable task database only                                     |
| `npm ci`                                                          | Passed; audit reported zero vulnerabilities                                     |
| `npm run format:check`                                            | Passed                                                                          |
| `npm run lint`                                                    | Passed                                                                          |
| `npm run typecheck`                                               | Passed                                                                          |
| `npm test`                                                        | One web test passed                                                             |
| `npm run build`                                                   | Production build passed                                                         |
| `uv run python scripts/smoke.py` with database URL                | API/web boot, both liveness endpoints, production page and readiness 200 passed |
| `uv run python scripts/smoke.py` without database URL             | Same boot/page checks and readiness 503 passed                                  |
| `git diff --check`                                                | Passed                                                                          |

The Python suite includes 11 real PostgreSQL integration tests. Coverage includes
all 49 source/target state pairs in the domain and a direct-SQL matrix; concurrent
version numbering; one winner among competing run transitions; stale revisions;
commit/read through separate connections; caller rollback; missing references;
SQL immutability/identity/timestamp guards; migration round-trip with seeded data;
metadata drift and explicit check-constraint name checks; and real API readiness.
API failure tests verify unavailable/unconfigured databases and a stalled query
produce 503 without breaking liveness or exposing driver details.

Final inspection caught a doubled-prefix constraint naming issue that Alembic's
automatic drift check did not report. The migration was corrected and an explicit
metadata/constraint-name integration check added. Final test results above include
that check. Formatting, typing and a raw-SQL test parameter typing issue were also
resolved before the final passing checks.

CI now starts PostgreSQL before tests, applies/checks migrations, sets the test URL,
and runs the full suite and readiness smoke checks. **Hosted GitHub Actions was not
run for these uncommitted changes.** Local commands passed; no push was performed.

The database catalog confirmed zero remaining `runveil_test_*` databases after the
suite. Removed only the task-created `runveil-phase1a` container, network and volume
with `docker compose -p runveil-phase1a down --volumes` using the same local test
variables above. Smoke servers terminated automatically. Existing project services
and data were left intact.

## Remaining concerns

- Phase 1 is incomplete: ordered steps/events, checkpoints and invocation/tool-call
  records remain. Current timestamps do not reconstruct every transition.
- No execution or domain HTTP interface exists. The web remains the Phase 0 console.
- Configuration is opaque JSON without provider/tool-specific validation. Never
  store credentials there; secrets and retention policies remain future work.
- Trigger guards protect normal writes, not against a database owner disabling them.
  Production role separation, privileges and migration deployment remain future work.
- Integration tests require CREATEDB. A killed test process can leave a temporary
  `runveil_test_*` database; ordinary successful/failed-test teardown cleans it up.
- The existing ESLint 9 deprecation warning remains; no unrelated frontend dependency
  changes were made. Final public-name clearance and license are still unresolved.

## Recommended next slice

After review, implement Phase 1B's ordered steps/execution events and checkpoints,
first documenting their atomic transaction/ordering boundary. Prove ordering and
checkpoint restoration before provider or execution-loop work.

## Files created

- `alembic.ini`
- `docs/adr/0003-phase-1a-persistence.md`
- `docs/operations/PERSISTENCE.md`
- `docs/operations/PHASE_1A.md`
- `packages/agent_core/pyproject.toml`
- `packages/agent_core/src/runveil_core/__init__.py`
- `packages/agent_core/src/runveil_core/agents.py`
- `packages/agent_core/src/runveil_core/errors.py`
- `packages/agent_core/src/runveil_core/py.typed`
- `packages/agent_core/src/runveil_core/runs.py`
- `packages/agent_core/tests/test_domain.py`
- `packages/persistence/migrations/env.py`
- `packages/persistence/migrations/script.py.mako`
- `packages/persistence/migrations/versions/0001_agents_and_runs.py`
- `packages/persistence/pyproject.toml`
- `packages/persistence/src/runveil_persistence/__init__.py`
- `packages/persistence/src/runveil_persistence/database.py`
- `packages/persistence/src/runveil_persistence/models.py`
- `packages/persistence/src/runveil_persistence/py.typed`
- `packages/persistence/src/runveil_persistence/repositories.py`
- `packages/persistence/tests/conftest.py`
- `packages/persistence/tests/test_configuration.py`
- `packages/persistence/tests/test_persistence.py`
- `packages/persistence/tests/test_readiness.py`

## Files modified

- `.env.example`
- `.github/workflows/ci.yml`
- `ARCHITECTURE.md`
- `CONTRIBUTING.md`
- `README.md`
- `ROADMAP.md`
- `apps/api/pyproject.toml`
- `apps/api/src/runveil_api/health.py`
- `apps/api/src/runveil_api/main.py`
- `apps/api/tests/test_health.py`
- `pyproject.toml`
- `scripts/smoke.py`
- `uv.lock`
