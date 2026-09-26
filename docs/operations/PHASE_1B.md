# Phase 1B handoff

Date: 2026-09-26. Implemented and stopped for review. No commit or push.

## Implementation summary and scope

Inspected the clean repository, root AGENTS instructions, charter, architecture,
roadmap, accepted ADRs, Phase 1A implementation/tests and existing handoff. The
current request supersedes the preserved charter's original Phase 0-only request.

Implemented the roadmap's coherent Phase 1B slice: immutable ordered run steps,
execution events and checkpoint persistence. Added migration 0002, typed core
snapshots, an atomic repository boundary, bounded history readers and PostgreSQL
integrity guards. Lifecycle writes now create events in the same transaction,
including direct SQL writes. Existing Phase 1A runs receive an explicitly
incomplete baseline, not invented historical transitions.

Added five PostgreSQL integration tests and one focused domain test. Extended the
existing migration and raw-SQL transition tests for the new tables/events. No new
packages, dependencies, HTTP routes or web features were needed. Phase 1 remains
incomplete: separate ModelInvocation and ToolCall records are the next Phase 1C
slice. No providers, execution loop, worker or automatic resume were added.

## Key decisions

See [ADR 0004](../adr/0004-execution-history.md) and
[persistence operations](PERSISTENCE.md) for the contracts and usage example.

- The caller owns the transaction. A run lock serializes a recorded step, its two
  events and full checkpoint; both lifecycle revision and history sequence must
  match the caller's decision. History-dependent transitions can check sequence too.
- Event order is per run, starts at one and rolls back without committed gaps.
  Immutable rows, composite foreign keys and checkpoint guards preserve boundaries.
- Checkpoints contain versioned opaque JSON state, a step and event watermark, and
  historical run revision/status. Loading restores a snapshot; safe execution
  recovery is explicitly not implemented. Unknown schema versions fail closed.
- The migration locks runs against writes while creating the baseline and installing
  lifecycle emission, preventing changes from falling between those operations.
- Boundaries are completed records, not in-flight invocation identities or retry
  attempts. Those concepts remain for the next reviewed persistence slice.

## Verification commands and results

Environment: macOS, Python 3.12.14, uv 0.12.19, Node 24.19.0,
PostgreSQL 17.9 in Docker. Node 24's executable directory was added to PATH:

```sh
export PATH=/Users/taom/.nvm/versions/node/v24.19.0/bin:$PATH
POSTGRES_USER=runveil POSTGRES_PASSWORD=runveil-local-only POSTGRES_DB=runveil POSTGRES_PORT=55432 docker compose -p runveil-phase1b up -d --wait --wait-timeout 90
export DATABASE_URL='postgresql+psycopg://runveil:runveil-local-only@127.0.0.1:55432/runveil'
export RUNVEIL_TEST_DATABASE_URL='postgresql+psycopg://runveil:runveil-local-only@127.0.0.1:55432/postgres'
```

Docker Desktop was initially stopped and was started. Only the task-specific
Compose project/database was used for verification. Existing data and `.env`
were not changed. The pre-existing virtualenv had executable paths pointing to an
old checkout location; a locked reinstall repaired it without dependency changes.

| Command                                                    | Result                                                             |
| ---------------------------------------------------------- | ------------------------------------------------------------------ |
| `uv sync --locked --all-packages`                          | Passed; existing virtualenv paths subsequently needed repair       |
| `uv sync --locked --all-packages --reinstall`              | Passed; same locked versions, executables repaired                 |
| `uv run ruff format --check .`                             | Passed; 41 files                                                   |
| `uv run ruff check .`                                      | Passed                                                             |
| `uv run mypy`                                              | Passed; 25 source files                                            |
| `uv run pytest` with test URL above                        | 88 passed, no skips; includes 16 real PostgreSQL integration tests |
| `uv run alembic upgrade head`                              | Passed from empty task database                                    |
| `uv run alembic current`                                   | `0002 (head)`                                                      |
| `uv run alembic check`                                     | No new upgrade operations detected                                 |
| `uv run alembic downgrade 0001` then upgrade/current/check | Passed on the task database only; final migration verified         |
| `npm ci`                                                   | Passed; zero audit vulnerabilities                                 |
| `npm run format:check`                                     | Passed                                                             |
| `npm run lint`                                             | Passed                                                             |
| `npm run typecheck`                                        | Passed                                                             |
| `npm test`                                                 | One web test passed                                                |
| `npm run build`                                            | Production build passed                                            |
| `uv run python scripts/smoke.py` with database URL         | API/web boot, liveness, production page and readiness 200 passed   |
| `env -u DATABASE_URL uv run python scripts/smoke.py`       | API/web boot, liveness, production page and readiness 503 passed   |
| `git diff --check`                                         | Passed                                                             |

Tests prove checkpoint restoration through a separate engine, immutable nested
state, unknown-schema rejection, bounded ordered history reads, post-checkpoint
lifecycle changes, rollback of the complete boundary/lifecycle write, invisibility
before commit, reusable rolled-back positions, stale-decision rejection, one
winner for competing writers, direct-SQL guards and lifecycle emission, same-run
checkpoint correlation, populated Phase 1A upgrade/downgrade/re-upgrade, empty
migration round-trip and metadata/constraint-name agreement.

Initial checks caught generated SQL whitespace and a duplicate test module name;
those were corrected before the final passing checks. Final review added the
migration write lock and reran the Python checks. npm reported the existing ESLint
9 deprecation and install-script policy notices; no dependencies were changed.
Hosted GitHub Actions was not run. Existing CI already runs these Python tests and
migrations, so its configuration required no change.

Confirmed zero remaining `runveil_test_*` databases, then removed only the
`runveil-phase1b` container, network and volume with the same Compose variables and
`docker compose -p runveil-phase1b down --volumes`. Smoke servers stopped themselves.

## Files created

- `docs/adr/0004-execution-history.md`
- `docs/operations/PHASE_1B.md`
- `packages/agent_core/src/runveil_core/history.py`
- `packages/agent_core/tests/test_history_domain.py`
- `packages/persistence/migrations/versions/0002_execution_history.py`
- `packages/persistence/src/runveil_persistence/history.py`
- `packages/persistence/tests/test_history.py`

## Files modified

- `ARCHITECTURE.md`
- `README.md`
- `ROADMAP.md`
- `docs/operations/PERSISTENCE.md`
- `packages/persistence/src/runveil_persistence/models.py`
- `packages/persistence/src/runveil_persistence/repositories.py`
- `packages/persistence/tests/test_persistence.py`

## Remaining concerns and next slice

Opaque checkpoint content has no runtime-specific schema, payload limit, redaction
or retention policy yet. Callers must supply safe JSON without credentials or
private reasoning. Database guards protect structural integrity, not against
privileged SQL clients forging content or disabling triggers. Multi-query reads
are not a coherent snapshot at READ COMMITTED; future execution decisions must
validate both revision and history position. Worker ownership, side-effect
idempotency and executable recovery remain later-phase work.

Migration 0002 pauses run writes and backfills one row per existing run; production
rollout sizing and role separation remain deployment work. Downgrading destroys
history, and re-upgrading cannot reconstruct it. The original public-name and
license decisions remain unresolved.

After review, implement **Phase 1C: model-invocation and tool-call records** with
durable identities, typed persistence and explicit run/step correlation. Keep
actual provider/tool calls and execution behavior out of that persistence slice.
