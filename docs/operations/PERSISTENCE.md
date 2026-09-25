# Persistence operations — Phase 1A

## Configuration and migration

Export `DATABASE_URL` using the `postgresql+psycopg://` scheme, a database name,
and the correct credentials/host/port. Percent-encode special characters in URL
credentials. `.env.example` provides local-only examples. Python does not read
`.env` implicitly. Do not commit real database credentials.

From the repository root, after `uv sync --locked --all-packages`:

```sh
uv run alembic upgrade head
uv run alembic current
uv run alembic check
```

Revision `0001` creates definitions, versions and runs, their constraints/indexes,
and immutability/lifecycle trigger functions. A downgrade to `base` **deletes all
three tables and their data**. Round-trip migration tests use disposable databases;
never use downgrade as an ordinary developer reset. Production migration execution
and separate runtime/migration roles are future deployment work.

Alembic's metadata drift check covers tables/indexes and supported constraints; it
does not validate trigger bodies. Direct-SQL integration tests verify those guards.

## Repository usage

These are Python APIs only; there are no HTTP creation/transition routes yet.
Use a distinct session per task. The caller chooses the transaction boundary:

```python
from sqlalchemy.ext.asyncio import async_sessionmaker
from runveil_core.runs import RunStatus
from runveil_persistence.database import create_engine, database_url
from runveil_persistence.repositories import AgentRepository, RunRepository


async def example() -> None:
    engine = create_engine(database_url())
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions.begin() as session:
            agents = AgentRepository(session)
            agent = await agents.create("Controlled coding fixture")
            version = await agents.create_version(
                agent.id, {"instructions": "Investigate the supplied fixture"}
            )
            run = await RunRepository(session).create(version.id)
        async with sessions.begin() as session:
            started = await RunRepository(session).transition(
                run.id, RunStatus.RUNNING, expected_revision=run.revision
            )
            assert started.revision == 1
    finally:
        await engine.dispose()
```

This example records state only; it does not execute an agent. Repository methods
flush but never commit. Exceptions escaping `sessions.begin()` roll back all work
in that transaction. Domain results are detached, frozen snapshots; configuration
access returns a fresh nested copy. Persisted configuration is opaque JSON and
must not contain credentials. Typed provider/tool configuration arrives later.

`NotFound` means an entity/reference is absent. `InvalidTransition` means the
lifecycle edge is forbidden. `RevisionConflict` means a stale caller must reload
and reconsider its requested operation. Do not blindly retry a stale decision.
Unexpected constraint/database failures propagate from SQLAlchemy; rollback the
transaction before reuse. No transaction retry or queue delivery logic exists yet.

## Lifecycle and invariant boundaries

See ADR 0003 for all allowed transitions. Runs begin QUEUED at revision zero and
pin an immutable version ID. The first RUNNING transition fixes `started_at`;
terminal transitions set `finished_at`; each transition advances the revision and
`state_changed_at`. PostgreSQL is the time source for repository transitions.
The version number is allocated under a parent lock and is unique per definition.

Version updates/deletes and invalid run changes fail even through direct SQL.
Database owners can disable triggers; this is an integrity boundary, not a sandbox
or substitute for future least-privilege roles. No deletion/retention API exists.
There is no complete transition history until ordered events arrive in Phase 1B.

## Readiness and tests

`GET /health` reports process liveness. `GET /ready` checks database connectivity
with a two-second timeout, returns 200 on success and generic 503 on failure or
missing configuration. It does not assert the schema revision. Migrations never
run on API startup. The API disposes its engine on shutdown.

```sh
# URL must name an existing admin database; the role needs CREATEDB.
export RUNVEIL_TEST_DATABASE_URL='postgresql+psycopg://runveil:runveil-local-only@127.0.0.1:5432/postgres'
uv run pytest -m integration
```

Each integration test creates a unique `runveil_test_<uuid>` database, migrates it,
and drops only that database in fixture teardown. The database in the URL is used
for administrative connections and is never reset. No SQLite substitutes are used.
Missing test configuration produces explicit skips; unreachable or invalid configured
databases fail. Interrupted test processes can leave temporary databases behind;
inspect and remove only confirmed test leftovers. CI supplies the URL and executes
all tests after booting PostgreSQL and validating migrations.
