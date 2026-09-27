# ADR 0012: Bounded model retries with durable backoff

- Status: Accepted for Phase 5B
- Date: 2026-09-27

## Decision

Add an explicitly versioned `fixture-retry-v1` offline worker profile. Preserve
`fixture-v1` and version-2 configuration/checkpoint behavior. Configuration version
3 pins a run-wide model retry limit (0–3) and positive base backoff (1–60 seconds).
Checkpoint version 3 retains retries scheduled and the failed invocation to retry.
Retries use new invocation IDs, retain the same request, and link to the previous
failed invocation through the immutable `model.requested` event's `retry_of` field.
No provider request or hidden reasoning is added to error metadata.

Core decides retry eligibility: only an explicit `ProviderError(RATE_LIMITED)`,
with both pinned policy and a trusted operator retry grant, remaining retry
capacity and at least one remaining step. The operator grant is checked again
before dispatching a previously scheduled retry. The new offline profile guarantees this
failure happens before producing a response. This is not a claim that arbitrary
HTTP status/error codes prove safe replay. Hosted profiles are not enabled.
Timeouts, unknown exceptions, unavailable providers, invalid responses, tool
errors and interrupted/uncertain invocations remain terminal without retry.
Each failed attempt and each subsequent attempt consumes one invocation step.

Scheduling is one fenced database transaction: complete the failed invocation,
checkpoint incremented retry count, append `retry.scheduled` with source ID/count/
eligibility time, transition RUNNING → RETRYING, set job eligibility and release
the lease. Rollback leaves the original intent unresolved. Backoff is
`base_seconds * 2 ** (retry_count - 1)`, bounded by the policy limits (maximum
240 seconds). No jitter or in-process sleeping is needed for this offline profile.
Migration 0005 adds job eligibility; existing jobs remain immediately eligible.

Polling excludes future eligibility and includes RETRYING. Resumption validates
the failed source, count, checkpoint and exact schedule/lifecycle event tail,
checks the database-clock deadline, transitions RETRYING → RUNNING, and checkpoints
the continuation atomically under the new claim. The next model request must
match the failed request. A crash after this resume checkpoint safely resumes it;
a crash after new request intent still fails as `execution_interrupted`.
Completed failure evidence is retained after eventual success. Terminal retry-limit
or step-limit failure keeps the provider error code; no extra retry is scheduled.

## Boundaries and trade-offs

This is a small PostgreSQL scheduling extension, not a general retry framework.
All writes keep existing claim/revision/history fences. Due time is checked again
on resumption, so a direct start cannot bypass the queue deadline. Cancellation
while RETRYING prevents further claims. Repeated delivery cannot duplicate a
schedule or reset counts. No heartbeat, broker, tool retry, output repair, hosted
idempotency, or token/cost/wall-time budget is introduced. Retry count is run-wide,
not reset after successful operations. Low-level repositories remain trusted
administrative APIs. The event link is validated by the repository; database owners
can bypass application-level retry policy, as with other execution-store rules.
