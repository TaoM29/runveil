# ADR 0008: Bounded persisted single-agent execution

- Status: Accepted for Phase 3
- Date: 2026-09-26

## Decision

Keep the execution loop and its narrow storage protocol in `runveil_core`; implement
that protocol using existing repositories in `runveil_persistence`. No core import
of SQLAlchemy, provider adapter, API or worker is needed. The store owns short
transactions and returns revision/event cursors. Provider calls happen only after
request intent commits and outside database transactions. Every outcome creates a
step and full checkpoint. Terminal outcome and lifecycle transition commit together.

Start only a QUEUED run with a validated, pinned version-1 runtime configuration.
Persist the task and initial conversation in a start checkpoint. Configuration pins
provider identity, model, system prompt, generation settings and maximum steps.
The caller supplies the matching provider implementation through a named binding;
credentials remain outside persisted configuration. Earlier opaque configurations
are not implicitly upgraded. Invalid configuration leaves the run untouched.

Count each model or tool invocation against `max_steps` (1–64). Check before
requesting either. Start and limit-exhaustion bookkeeping boundaries do not consume
this budget. A finish on the last allowed invocation succeeds; a tool action without
remaining capacity fails before tool dispatch. This is a step bound, not token,
cost, elapsed-time or retry accounting. Enforce the model request deadline in the
loop as well as any provider adapter deadline.

Advertise only `fixture.info`, accepting exactly an empty argument object and
returning fixed public fixture metadata. It has no filesystem, shell or network
capability. No injectable arbitrary tool callback or generic tool registry is
introduced before Phase 4. Preserve ordered system/task/validated assistant/tool
messages; final result, counts and safe failure codes are checkpointed. Provider
failures and invalid actions fail the model record; invalid fixture arguments fail
the tool record. Never persist invalid model content or raw exceptions. Unknown
provider exceptions become `provider_unavailable`; cancellation propagates.

## Concurrency and limitations

Each write uses the cursor returned by the preceding committed boundary, never a
fresh cursor to force a stale decision through. Competing starts cannot both call a
provider. Cancellation or competing history writes reject late results; callers
must not retry automatically. Process interruption and task cancellation can leave
RUNNING runs and REQUESTED records. Existing runs cannot be resumed by this loop.
These records are reconstruction evidence, not a recovery or exactly-once claim.
A race after intent commits can still send a provider request after cancellation;
remote calls cannot be made atomic with PostgreSQL lifecycle changes.

Checkpoints use a versioned runtime state inside the existing versioned opaque
checkpoint envelope; no migration is needed. Completed runs can be reconstructed
from database snapshots and correlated invocation records without the provider.
No HTTP execution endpoint, worker, lease, retry, approval or production tool
policy is added. Phase 2 hosted acceptance was separately pending when this
decision was accepted; explicit Phase 3 authorization permitted offline runtime
implementation before that live gate. The gate has since closed through a
[user-reported hosted invocation](../operations/PHASE_2B.md#subsequent-hosted-live-acceptance--complete).
