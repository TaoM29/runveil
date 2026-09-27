# ADR 0011: Leased PostgreSQL fixture worker and conservative recovery

- Status: Accepted for Phase 5A
- Date: 2026-09-27

## Decision

Use PostgreSQL as the first durable work queue. Enroll a queued run with its task
and the fixed `fixture-v1` execution profile in the same transaction that creates
it. One job per run makes repeated delivery of a run ID harmless. Polling uses
`FOR UPDATE SKIP LOCKED`; no separate broker/outbox consistency problem is added.
This does not implement submission deduplication across independently created runs.

A claim has a random ownership token and a database-clock expiry. All execution
store writes lock the run first, check ownership and expiry, then renew the lease
in the same transaction as the boundary. Unclaimed stores refuse enrolled runs.
The fixed 660-second lease exceeds the runtime's maximum 600-second provider
call. There is no heartbeat task: stalled operations lose ownership at expiry;
late outcomes cannot commit even before a replacement claims the run. Tokens are
internal capability identifiers, never model context or command output. Lifecycle
cancellation continues to invalidate execution through revision/history checks.
Low-level repositories remain trusted administrative APIs, not an authorization
boundary against database owners.

Runtime checkpoint version 2 records the next tool action and its originating
model invocation. Recovery validates checkpoint revision and event tail under the
run lock. Resume only enrolled version-2 checkpoints under the same fixed profile.
Older checkpoints remain inspectable, but are not automatically adopted. A clean
checkpoint resumes the next operation without repeating a committed outcome. One
unresolved request after the checkpoint is completed as `execution_interrupted`,
with an atomic failed checkpoint and terminal transition. Its consumed step is
counted once. The request may or may not have executed: recovery never replays it.
Unexpected history or unsupported state fails closed for operator investigation.

The worker app owns the profile and process loop, using core execution and the
persistence adapter. `fixture-v1` pins a deterministic context-driven scripted
provider and the built-in `fixture.info` binding/policy. Unlike an in-memory script
index, persisted context selects the next response after restart. Enrollment and
execution both verify the complete runtime configuration. Changing these semantics
requires a new profile ID. No hosted/provider credentials, arbitrary bindings,
repository paths, mutation tools or external effects are accepted by this worker.

## Trade-offs and remaining scope

This is durable ownership and conservative crash recovery, not exactly-once
external execution, safe retry, an SQS integration or a production scheduler.
Cancellation and process death can leave a lease until expiry. A pause after a
committed request can still allow a stale process to execute its pure fixture;
only its database writes are fenced. Real providers and repository recovery need
explicit attempt/idempotency and workspace/implementation identity policies.
Automatic retries/backoff, token/cost/wall-time budgets and broader worker profiles
remain subsequent Phase 5 slices. Existing step and per-call limits still apply.
