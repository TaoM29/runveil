# ADR 0003: Immutable versions and transactional run lifecycle

- Status: Accepted for Phase 1A
- Date: 2026-09-25

## Context and scope

The roadmap calls for a first persistence slice before events and checkpoints.
Phase 1A introduces agent definitions, immutable versions, runs, lifecycle rules,
PostgreSQL repositories and an initial migration. It does not execute agents or
expose creation/transition HTTP endpoints. The API gains a database readiness probe.

## Decisions

Keep domain snapshots and transitions in `packages/agent_core`, independent of
FastAPI and SQLAlchemy. Put PostgreSQL mappings, repositories and migrations in
`packages/persistence`. Both packages now have concrete responsibilities. Use
SQLAlchemy 2 async sessions with psycopg 3 and Alembic. Callers own transaction
commit/rollback; repositories flush changes without committing. Do not share a
session between concurrent tasks.

Agent versions are immutable from creation, a stronger and simpler rule than
freezing only after first use. Changes create a new version. PostgreSQL rejects
version UPDATE and DELETE, even through direct SQL. Definition and version
references use restrictive foreign keys. Allocate sequential version numbers
under a lock on the parent definition; uniqueness is also database-enforced.
Configuration is an opaque JSON object until the provider/tool phases define its
schema. Domain snapshots retain canonical JSON text and return detached decoded
copies, preventing nested mutation from changing the snapshot. Configuration must
not contain credentials; it is not encrypted secret storage.

New runs start QUEUED at revision zero. A transition requires the caller's expected
revision, locks the run row, checks that revision, then validates the domain
transition. Reject stale writes instead of silently applying them to a newer state.
Return immutable snapshots rather than live ORM objects. PostgreSQL also guards
run transitions, revision increments, identity and lifecycle timestamps so raw SQL
cannot bypass the state graph. Terminal states cannot transition again.

Allowed transitions:

- QUEUED → RUNNING or CANCELLED.
- RUNNING → WAITING_FOR_APPROVAL, RETRYING, SUCCEEDED, FAILED or CANCELLED.
- WAITING_FOR_APPROVAL → RUNNING, FAILED or CANCELLED.
- RETRYING → RUNNING, FAILED or CANCELLED.

Persist creation time, most recent state-change time, first start time and terminal
time as timezone-aware values. Use the database clock for repository transitions;
reject backwards timestamps. Full transition history is explicitly deferred to
Phase 1B's ordered execution events. Approval/retry state names do not implement
approval or retry behavior.

`GET /health` remains unconditional liveness. `GET /ready` reports database
connectivity only, with a bounded timeout and generic 503 response when unavailable
or unconfigured. Migrations are explicit operator/CI actions, never startup work.

## Alternatives and trade-offs

A mutable draft-version lifecycle adds policy and races without a current use case.
Optimistic updates alone could work, but row locks simplify version allocation and
consistent lifecycle validation. Database guards duplicate a small state graph;
exhaustive domain and direct-SQL tests must detect drift. Keep the initial migration
self-contained rather than importing future-changing application rules.

A single API-owned persistence module would later couple the worker to the API.
Generic repository interfaces, queues, events and automatic migration on startup
are deferred until their actual slice. Tests use real PostgreSQL, not SQLite.

## Consequences

Integration tests create randomly named temporary databases from an explicitly
provided test admin URL, migrate them, and drop only those databases. No tests
truncate or downgrade the developer database. Production roles, privilege hardening,
retention/deletion policy and transaction retries remain future work. A database
owner can bypass triggers; these invariants are not a security sandbox.

Implementation references: [SQLAlchemy session guidance](https://docs.sqlalchemy.org/en/20/orm/session_basics.html)
and [Alembic async connection sharing](https://alembic.sqlalchemy.org/en/latest/cookbook.html#using-asyncio-with-alembic).
