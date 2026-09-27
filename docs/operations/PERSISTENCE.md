# Persistence operations — Phase 1C

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

Revision `0001` creates definitions, versions and runs with lifecycle guards.
Revision `0002` adds steps, events, checkpoints and history triggers, and seeds an
incomplete baseline for existing runs. Revision `0003` adds model-invocation and
tool-call tables and request/outcome guards. Downgrading to `0002` deletes those
records but preserves history/checkpoints, leaving any UUID references in event
payloads unresolved. Re-upgrade cannot reconstruct deleted records.
Downgrading to `0001` **deletes all history
and checkpoint data** while preserving agents/runs. A downgrade to `base`
**deletes all domain tables and their data**. Round-trip migration tests use disposable databases;
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
must not contain credentials. Phase 2A model contracts can be stored inside invocation JSON; agent-version
configuration and tool policy remain opaque.

`NotFound` means an entity/reference is absent. `InvalidTransition` means the
lifecycle edge is forbidden. `RevisionConflict` means a stale caller must reload
and reconsider its requested operation. Do not blindly retry a stale decision.
Unexpected constraint/database failures propagate from SQLAlchemy; rollback the
transaction before reuse. These repositories do not retry transactions. Durable
queue selection and execution fences are provided by the [worker/store layer](WORKER.md).

## Lifecycle and invariant boundaries

See ADR 0003 for all allowed transitions. Runs begin QUEUED at revision zero and
pin an immutable version ID. The first RUNNING transition fixes `started_at`;
terminal transitions set `finished_at`; each transition advances the revision and
`state_changed_at`. PostgreSQL is the time source for repository transitions.
The version number is allocated under a parent lock and is unique per definition.

Version updates/deletes and invalid run changes fail even through direct SQL.
Database owners can disable triggers; this is an integrity boundary, not a sandbox
or substitute for future least-privilege roles. No deletion/retention API exists.
New runs have complete lifecycle history through transactional database triggers.
Runs migrated from 1A start with a `run.snapshot` baseline that explicitly marks
prior history incomplete.

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

## Execution boundaries and checkpoint restoration

`HistoryRepository` provides `record_step`, `events`, `steps` and
`latest_checkpoint`. A step is an immutable recorded boundary, not an in-flight
operation or tool invocation. Each boundary has a full checkpoint; schema version 1
stores an opaque JSON object and readers reject unsupported versions. Select safe
content: never persist secrets, credentials or hidden model reasoning. The API
does not redact arbitrary caller JSON. See [ADR 0004](../adr/0004-execution-history.md).

For a new run (created at event 1), starting it creates event 2:

```python
from runveil_persistence.history import HistoryRepository

# Inside the caller's transaction, after starting a newly created run:
history = HistoryRepository(session)
checkpoint = await history.record_step(
    run.id,
    kind="fixture.response",
    details={"summary": "Deterministic fixture response"},
    state={"messages": [{"role": "assistant", "content": "Fixture"}], "iteration": 1},
    expected_revision=1,
    expected_sequence=2,
)
# The step and its two events are now flushed, still uncommitted.
finished = await RunRepository(session).transition(
    run.id,
    RunStatus.SUCCEEDED,
    expected_revision=checkpoint.run_revision,
    expected_sequence=checkpoint.event_sequence,
)
# Commit on exiting sessions.begin(); any escaping exception rolls everything back.
```

Both revision and sequence must match for boundary writes. Lifecycle transitions
accept an optional `expected_sequence`; supply it whenever the decision depends on
history. Revision-only transitions retain the original lifecycle contract. Never
blindly replay a failed write or external operation. Reload and reconsider after
`RevisionConflict`; roll back after any database failure. Use READ COMMITTED, one
session per task, and short transactions without external calls.

After reconnecting, `await history.latest_checkpoint(run.id)` returns the newest
persisted snapshot, or `None` if no boundary was recorded. Unknown runs raise
`NotFound`. Load the current run and pinned agent version separately. Read
`await history.events(run.id, after_sequence=checkpoint.event_sequence)` for the
post-checkpoint tail; the checkpoint's lifecycle state is historical. These reads
are not a coherent multi-query snapshot under READ COMMITTED; subsequent writes
must validate revision and sequence. Loading is not execution, replay, worker
ownership or side-effect deduplication.

`events(..., after_sequence=0, limit=100)` and
`steps(..., after_number=0, limit=100)` return ascending pages. Limits must be
1–1000; cursors are exclusive. Continue using the last returned position. Empty
pages are valid. Ordering is per run by sequence/number, never by wall-clock time.
The checkpoint watermark is its `checkpoint.created` event position, including
all history through that boundary.

Database triggers reject history UPDATE/DELETE, invalid step order and mismatched
checkpoint links. Event sequence allocation and lifecycle events are database-owned.
The repository method provides atomic step/event/checkpoint assembly; arbitrary
manual inserts are not a supported substitute. Structural guards do not authorize
SQL clients, validate the meaning of opaque state, or prevent database owners from
disabling triggers. No retention or deletion API is implemented.

## Model-invocation and tool-call records

`InvocationRepository` exposes `request_model`, `get_model`, `complete_model`,
`request_tool`, `get_tool` and `complete_tool`. Lookups require both run and record
ID; IDs can be recovered from the ordered events' `record_id` payloads. Unknown or
wrong-run records raise `NotFound`. Request UUIDs are caller-supplied; keep them
stable across uncertain writes and inspect persisted state before taking action.
Duplicate IDs raise a database integrity error, not an idempotent success response.
Roll back on database errors. Persistence does not make external actions safe to
repeat.

For a new run already started at revision 1/event 2, in a caller-owned transaction:

```python
from uuid import uuid4
from runveil_persistence.invocations import InvocationRepository

records = InvocationRepository(session)
requested = await records.request_model(
    run.id,
    invocation_id=uuid4(),
    provider="fixture",
    model="scripted",
    request={"messages": [{"role": "user", "content": "Fixture task"}]},
    expected_revision=1,
    expected_sequence=2,
)
# Commit intent before any future external operation. No model is called here.
```

In a later transaction, assuming the run/history are unchanged:

```python
completed = await InvocationRepository(session).complete_model(
    run.id,
    requested.id,
    result={"summary": "Fixture response"},
    state={"messages": [{"role": "assistant", "content": "Fixture response"}]},
    expected_revision=1,
    expected_sequence=requested.requested_event_sequence,
)
```

This writes `model.completed`, a matching step and a full checkpoint, and changes
the record to SUCCEEDED atomically. For failure, pass `error_code="provider_timeout"`
instead of `result`. Exactly one result object or error code is required. Error
codes are lowercase identifiers up to 64 characters; do not pass raw exception
strings. A completed record is immutable. The historical request snapshot returned
earlier remains REQUESTED; reload by ID to inspect the latest persisted outcome.

Tool methods use the same contract, with `tool_call_id`, `tool_name` and `arguments`
at request time. An optional `model_invocation_id` must refer to a succeeded model
record in this run. This is provenance only: it does not prove the model selected
that exact tool or authorize execution. Provider/tool-specific validation belongs
to the core runtime and tool registry. A source-less tool request is permitted for future native callers.

Both request and outcome writes require RUNNING plus matching revision/sequence.
A pending request remains visible after cancellation; late completion is rejected.
These low-level repositories do not enforce worker ownership or retry policy; use
`PostgresExecutionStore` for enrolled execution. The worker layer owns claims,
leases and bounded model retry scheduling.
The operation status REQUESTED does not say whether an external call started.
Recorded timestamps are persistence times, not measured model/tool latency.

Request/outcome events contain record identity without duplicating request,
result or error content. A retry model request additionally stores `retry_of` in
its event; the repository verifies a failed rate-limited model source in the same
run and identical provider/model/request. It still requires the caller to enforce
scheduling and retry limits. They have no step number because the completed boundary
is allocated afterwards; the record's `step_number` and step's `record_id` details
supply correlation. The checkpoint watermark includes the outcome event, and the
record and checkpoint become visible together at commit. Inputs are detached and
validated before writes. JSON objects are still opaque selected data; do not place
credentials or hidden reasoning in them. See
[ADR 0005](../adr/0005-invocation-records.md) for limits and migration trade-offs.

## Phase 2A normalized model payloads

See [model operations](MODELS.md) for the versioned request/response contracts.
Pass `request.model_dump(mode="json")` into `request_model`, and the validated
response's dump into `complete_model`. Restore with
`ModelRequest.model_validate_json(record.request_json)` or
`ModelResponse.model_validate_json(record.result_json)` (after checking for a
successful result). Existing Phase 1 payloads are not automatically converted.
Commit intent before calling the provider; validate its action outside transactions
and persist a selected outcome with the current revision/sequence. Validation does
not authorize tool execution. Neither provider calls nor action parsing are added
to repository methods. The integration test demonstrates this boundary without
implementing runtime orchestration.
