# Architecture

## Implemented through Phase 4A

```mermaid
flowchart LR
    Browser --> Web[Next.js console :3000]
    Client[HTTP client] --> API[FastAPI :8000]
    Compose[Docker Compose] --> PG[(PostgreSQL :5432)]
    API -->|readiness query| PG
    Persistence[Async repositories and Alembic] --> PG
    Persistence --> Domain[Immutable versions, run lifecycle and history snapshots]
    Scripted[Offline scripted provider] --> Contracts[Model contracts and action validation]
    Hosted[HTTPX Chat Completions adapter] --> Contracts
    Hosted --> Endpoint[Configured OpenAI-compatible endpoint]
    Runtime[Bounded core execution loop] --> Contracts
    Runtime --> Store[PostgreSQL execution store]
    Store --> Persistence
    Runtime --> Tools[Typed registry and explicit grants]
    Tools --> Fixture[Registered read-only fixture tool]
```

Both applications expose `GET /health` with a typed/structured service identity.
These endpoints report liveness. The API also has `/ready`, a bounded database
connectivity probe. PostgreSQL has its own Compose health check. Schema migration
is an explicit operation. The web console remains the Phase 0 foundation; there
are no domain HTTP endpoints or web-to-API requests yet.

The root uv workspace locks Python dependencies in `uv.lock`; the API uses a src
layout and is installed as a real package. The npm workspace uses one root lockfile.
Python 3.12 and Node 24 are the initial supported interpreter lines. Explicit
minor-version adoption is preferred to untested claims of support for all future
Python versions. FastAPI/Pydantic and Next.js/React/TypeScript/Tailwind establish
the app boundaries. Ruff, strict mypy, ESLint, strict TypeScript, Prettier, pytest,
Vitest and process smoke checks form the quality baseline.

## Frozen initial boundaries

- Python backend; PostgreSQL is the future system of record.
- Build the runtime directly, initially for one agent per run.
- Next.js is the console; the runtime remains independent of UI concerns.
- Docker provides local dependencies and later controlled task environments.
- AWS is the deployment target, with Terraform managing infrastructure.
- No agent behavior, provider calls, tools, authentication or cloud deployment in Phase 0.

See [ADR 0001](docs/adr/0001-custom-runtime.md) and
[ADR 0002](docs/adr/0002-foundation-boundaries.md).

## Target architecture — not implemented

```mermaid
flowchart TD
    Web[Web console] --> API[Control API]
    API --> PG[(PostgreSQL)]
    API --> Queue[Queue / SQS]
    Queue --> Worker[Worker]
    Worker --> Runtime[Custom single-agent runtime]
    Runtime --> PG
    Runtime --> Providers[Provider adapters]
    Runtime --> Tools[Typed authorized tools / MCP adapter]
    Tools --> Sandbox[Disposable task container]
    Runtime --> Telemetry[OpenTelemetry / execution events]
    Evals[Evaluation harness] --> Runtime
```

The API will accept work rather than run long tasks within an HTTP request.
Runtime domain code belongs in `packages/agent_core`; providers, tool execution,
evaluation and observability receive separate packages only when cohesive
implementations exist. `apps/worker` will own process/queue integration.
Dependency direction should point from apps and adapters toward domain contracts,
never from the domain toward FastAPI or Next.js.

Phase 1A adds `AgentDefinition`, immutable `AgentVersion` and `Run` snapshots in
`runveil_core`. Configuration is stored as opaque JSON without provider/tool
semantics. `runveil_persistence` owns SQLAlchemy mappings, psycopg async connections,
concrete repositories and Alembic migration 0001. The core imports neither the API
nor the persistence adapter. API lifecycle code owns and disposes its readiness engine.

Repository callers own transactions. Parent-row locks serialize version numbering;
run-row locks plus required expected revisions reject stale transitions. PostgreSQL
triggers enforce immutable versions and the same state graph as the domain. Store
creation, most recent transition, first start and terminal timestamps. See
[ADR 0003](docs/adr/0003-phase-1a-persistence.md) for the transition table and trade-offs.

Phase 1B adds immutable `RunStep`, `ExecutionEvent` and `Checkpoint` snapshots,
ORM tables and migration 0002. The run row serializes all repository boundary
writes. `record_step` checks both expected revision and event sequence, then writes
the step, two events and full checkpoint in the caller's transaction. Database
triggers append lifecycle events and assign event order, including direct SQL
lifecycle writes. Existing runs receive an explicitly incomplete snapshot baseline.
Read APIs use bounded cursor pagination and latest-checkpoint lookup. See
[ADR 0004](docs/adr/0004-execution-history.md) for the transaction and restore contract.

Checkpoint loading restores opaque versioned JSON state and its event watermark;
it does not resume execution. The current run may have advanced since that snapshot.
Phase 1C adds `ModelInvocation` and `ToolCall`: persisted request identities and
one-time outcomes. Both use the run's revision/sequence boundary. Completion writes
an outcome event, then a correlated step/checkpoint, and finalizes the record in
one transaction. Optional tool provenance references a succeeded model invocation
in the same run. Migration 0003 adds the two tables and integrity guards without
rewriting Phase 1B history. See [ADR 0005](docs/adr/0005-invocation-records.md).

A requested record is evidence of intent, not a worker claim or proof of dispatch.
Phase 1C deferred durable workers and general tool authorization to later phases.
No new packages or HTTP routes were needed for Phase 1C.

Phase 2A adds provider-neutral Pydantic contracts and an async `ModelProvider`
protocol in `runveil_core`. `ScriptedProvider` consumes detached response/error
fixtures without network or retries. Responses normalize content, finish reason,
nullable usage and latency. A separate validator accepts exactly one structured
`tool_call` or `finish`, rejecting malformed/incomplete output and unadvertised
tool names. This does not authorize tools or validate arguments against tool
schemas. Contract JSON fits Phase 1C invocation records without a migration;
an integration test commits intent, calls outside a transaction, validates, then
persists/restores the outcome and checkpoint. See
[ADR 0006](docs/adr/0006-model-contracts.md).

Phase 2B adds `runveil_providers`, with one OpenAI-compatible Chat Completions
adapter using HTTPX. Operator configuration and credentials remain outside core
requests and persistence. JSON mode and an explicit action-schema instruction
preserve Phase 2A's envelope; callers still validate actions. The adapter owns and
closes its client, makes no retries, disables redirects/environment proxy settings,
bounds request/response bodies and enforces a network deadline. Cancellation
propagates; failures expose fixed codes. The wire boundary retains only selected
response fields and normalizes refusal, truncation, usage and latency. Native tool
calling, streaming and vendor-specific capability negotiation are not implemented.
See [ADR 0007](docs/adr/0007-hosted-provider.md) and
[provider operations](docs/operations/MODELS.md). An opt-in live command is available;
manual hosted acceptance is complete, with
[user-reported evidence](docs/operations/PHASE_2B.md#subsequent-hosted-live-acceptance--complete).

Phase 3 adds a bounded loop and storage protocol in `runveil_core.runtime`, with a
`PostgresExecutionStore` adapter in the persistence package. It starts only queued
runs, validates pinned configuration and checkpoints initial context. Model and
fixed fixture-tool invocations consume a shared step bound. Every request commits
before dispatch; outcomes checkpoint full context and final/error state. Terminal
outcomes and lifecycle transitions share one transaction. Provider calls have a
deadline and occur outside transactions. Stale writes and task cancellation
propagate; interrupted executions are not resumed or retried. The one fixture tool
has no filesystem/network capability. Runtime checkpoint state can be restored for
inspection independently of execution. See [ADR 0008](docs/adr/0008-minimal-runtime.md)
and [runtime operations](docs/operations/RUNTIME.md). No migration or domain HTTP
endpoint was needed; the CLI demonstration uses the same persisted loop.

Phase 4A replaces fixed dispatch with `runveil_core.tools`: Pydantic-derived
input/output schemas, a typed native handler binding and registry, 64 KiB payload
bounds, safe error codes and cooperative tool deadlines. Runtime configuration
version 2 pins tool names/permissions; a separate operator policy must also grant
them. Both default to deny. Only READ + PURE/READ_ONLY bindings are executable.
Tool offers are filtered and dispatch rechecks policy; persisted calls use the
selected name and existing atomic outcome/event/checkpoint boundaries. The fixture
is the sole built-in tool. No migration, dependency or package is added. See
[ADR 0009](docs/adr/0009-typed-tool-dispatch.md). Repository tools and filesystem
boundaries remain Phase 4B; trusted in-process handlers are not sandboxed.

Queue consistency, approvals and sandbox boundaries still require future ADRs and
tests; the target diagram does not claim those properties exist.

## Open decisions

- Public product/repository name and license.
- Future additional provider profiles/capabilities.
- Queue/database consistency and worker claim semantics.
- Sandbox threat model and AWS cost/deployment details.

These are reviewed in their relevant phase, not settled by empty abstractions.
