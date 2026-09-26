# ADR 0005: Durable model and tool request records

- Status: Accepted for Phase 1C
- Date: 2026-09-26

## Decision and scope

Complete Phase 1 with separate `ModelInvocation` and `ToolCall` domain snapshots,
PostgreSQL tables and repository methods. Keep this work inside the existing core
and persistence packages. No provider, tool dispatch, authorization, worker or
retry implementation is introduced.

Each request has a caller-supplied UUID, a run, an ordered request event, immutable
request data and a REQUESTED status. Model records identify provider and model;
tool records identify a tool and may reference a succeeded model invocation in the
same run. A request is persisted intent, not proof of dispatch or a worker claim.
The UUID supplies a durable local identity, not external-side-effect idempotency.
Duplicate UUID inserts fail rather than silently accepting a different request.

Requests can transition exactly once to SUCCEEDED with a JSON result or FAILED
with a bounded error code. Raw exceptions are not accepted as an error payload.
Request/result JSON remains opaque until the provider/tool phases define their
schemas. Callers must supply safe selected content, without credentials or hidden
reasoning. No automatic arbitrary-JSON redaction or semantic validation is claimed.

All repository writes lock the run first and require expected run revision and
event sequence. Only RUNNING runs accept requests or outcomes. The caller owns
commit/rollback, uses a separate session per task and keeps external work outside
transactions. Late outcomes after cancellation/pause are rejected; a pending record
is preserved as unresolved evidence. Reconciliation and replay policy come later.

Request events are `model.requested` and `tool.requested`. Completion writes
`model.completed`/`model.failed` or `tool.completed`/`tool.failed`, then uses the
Phase 1B boundary API to create a matching step and checkpoint, and finalizes the
request record in the same transaction. Request/outcome events identify the record
by UUID and have no step number: the completed step is allocated afterwards and
linked from the record. The checkpoint watermark includes the outcome event.
Step details also identify the record, enabling correlation in both directions.
Completed records and their original request fields cannot be rewritten/deleted.

Database guards validate request/outcome event identity and kind, current run
revision, completion step/checkpoint correlation and same-run model provenance.
Constraints enforce outcome shape and unique event/step ownership within each
record type. The repository provides atomic assembly; arbitrary SQL clients must
not assemble partial boundaries. As in earlier ADRs, database owners can bypass
guards; these are integrity rules, not authorization.

## Trade-offs and consequences

Persisting only completed receipts would lose the identity of interrupted work.
Adding leases, attempt graphs, retry keys, budgets or a generic operation framework
now would preempt later phases. Two concrete tables with a small shared mapping
mixin and private repository helpers cover the common record lifecycle without a
public generic execution abstraction. Model and tool request/outcome contracts stay
separate and can evolve independently.

Results and arguments use immutable JSON snapshots. Provider response normalization,
usage, latency and structured action validation arrive in Phase 2. Tool schemas,
policy and external idempotency arrive in their planned phases. Recorded timestamps
measure persistence boundaries and must not be presented as provider/tool latency.

Migration 0003 adds tables and guards without altering existing history. No
historical invocations are invented. Downgrade removes these records but leaves
Phase 1B history/checkpoints, including any event payload UUID references, intact;
those references cannot be reconstructed by re-upgrade. Downgrade is destructive
and belongs only in deliberate migration testing or an operator recovery plan.
