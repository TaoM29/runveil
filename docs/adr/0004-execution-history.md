# ADR 0004: Ordered execution boundaries and checkpoint state

- Status: Accepted for Phase 1B
- Date: 2026-09-26

## Context and scope

Phase 1A stores immutable versions and the latest run lifecycle state. Phase 1B
adds `RunStep`, `ExecutionEvent` and `Checkpoint`, without executing work. Separate
model-invocation and tool-call records remain a Phase 1C review slice before the
provider phase. This keeps history semantics reviewable without guessing provider,
tool or retry contracts. Phase 1 as a whole is not complete.

## Decision

Use the existing core and persistence packages. A step is an immutable record of
a meaningful execution boundary, with a per-run number, caller-supplied kind and
JSON details. It is not an in-flight job, tool identity or retry attempt. Each
`HistoryRepository.record_step` writes the step, `step.recorded` event,
`checkpoint.created` event and full checkpoint state together. Only RUNNING runs
can record boundaries. A caller can then pause or finish the run in the same
transaction. Recording approval decisions themselves is future work.

The caller still owns commit/rollback. Lock the run row before allocating step or
event positions; hold it until the transaction ends. Writes to one run serialize;
different runs use different locks. Use one session per task and PostgreSQL's
default READ COMMITTED isolation. No external calls belong inside this transaction.
At stronger isolation levels, callers may receive serialization errors; there is
no implicit retry. Multi-run transactions should lock runs in a consistent order.

`record_step` requires both expected lifecycle revision and event sequence. A
second boundary does not change the lifecycle revision, so revision alone cannot
reject a stale execution decision. Stale callers must reload and reconsider; do
not retry side effects. Lifecycle transitions retain their Phase 1A revision
contract and additionally accept `expected_sequence` for history-dependent
decisions. Future execution callers must supply it. Ordinary lifecycle-only
transitions can still use only the revision.

PostgreSQL allocates event sequences under the same run lock. The append-only log
starts at one per run, with no committed gaps from rolled-back transactions.
Sequence is the ordering authority, not timestamps or globally unique IDs. Composite
foreign keys keep event/step/checkpoint links in the same run. Triggers reject
history updates/deletes, out-of-order steps, and checkpoints that do not reference
a matching checkpoint event at the current running revision. Composite primary
keys support ordered reads and latest checkpoint lookup; no separate counter table
or speculative event bus is needed.

An AFTER trigger on run INSERT/UPDATE records `run.created` or `run.transitioned`
atomically, including direct-SQL lifecycle writes. Transition payloads contain the
previous and next states, revision and transition time. Migration 0002 seeds one
`run.snapshot` event for each existing run, including its current revision,
timestamps and version ID, with `history_complete: false`. It never fabricates
missing historical edges. Future lifecycle events follow that baseline. The
migration locks runs against writes until commit so no lifecycle change can slip
between baseline capture and trigger installation. Plan for that write pause when
applying it to a populated database.

A checkpoint has an event watermark, step, lifecycle revision/status and a full
JSON object supplied by the caller. Its run pins the immutable agent version.
Schema version 1 describes this opaque-state envelope; readers reject unknown
versions rather than silently treating them as empty state. No model conversation,
budget or tool-execution state schema is claimed yet. Core snapshots return fresh
nested JSON copies. Never store credentials or hidden model reasoning in these
records; callers must select safe content. Storage is not a secret store or a
redaction service.

Loading the latest checkpoint restores the persisted snapshot only. Its revision
may precede the current run after a pause, terminal transition or other lifecycle
change. A future runtime must inspect the current run, pinned version and event
tail, then use revision/sequence checks when writing its decision. Multiple reads
at READ COMMITTED are not a single consistent read snapshot. History alone does
not provide safe side-effect replay, worker ownership, delivery idempotency or
exactly-once execution.

## Alternatives and trade-offs

Application-only lifecycle events would miss direct SQL writes already supported
and tested by Phase 1A. Trigger emission preserves one atomic state/history write
path, at the cost of PostgreSQL-specific migration logic and integration tests.
Database sequences permit rollback gaps; a separate mutable counter would add
state while per-run indexed MAX lookups suffice for this initial slice.

One step plus one checkpoint per recorded boundary deliberately omits intermediate
in-flight records. Separate invocation/tool-call persistence can later represent
those identities without redefining completed boundaries as jobs. We do not expose
a generic event-append API yet; supported events have concrete producers.

Database guards enforce structural integrity, not authorization or truthfulness of
caller JSON. Privileged SQL clients can insert misleading content or disable
triggers. Least-privilege roles, retention, payload limits and runtime-specific
validation remain later work. The repository is the supported atomic boundary API;
manual SQL inserts must not be used to assemble partial execution boundaries.
Downgrade to 0001 destroys history/checkpoints while preserving agents and runs;
re-upgrade can recover only a new incomplete baseline, never the deleted history.
