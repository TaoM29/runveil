# ADR 0013: Durable elapsed-time execution budget

- Status: Accepted for Phase 5C
- Date: 2026-09-27

## Decision

Configuration/checkpoint version 4 enables a required `max_elapsed_seconds` integer
from 1 to 86400. Versions 2/3 retain their existing behavior without this budget.
The new offline `fixture-budget-v1` profile combines the existing retry fixture
with a 30-second budget; no hosted or repository replay profile is introduced.

Migration 0006 adds a nullable deadline to worker jobs. On the first RUNNING
transition, persist `started_at + max_elapsed_seconds` in the same transaction as
the start checkpoint. Initial queue time is excluded; execution, retry waits and
process downtime after first start are included. A database trigger prevents
changing an assigned deadline. Recovery verifies it against the immutable run
start time and pinned configuration. Existing jobs receive no deadline.

Database time is authoritative. Under the existing ownership/run-history locks,
check the deadline before request, outcome, retry-schedule and step-limit writes.
The runtime additionally checks after committed intent immediately before model
or tool dispatch, and after the call. Bound cooperative calls by the smaller of
remaining elapsed time and the existing per-call deadline, without changing the
persisted model request (retry request identity stays stable).

At expiry (`now >= deadline`), atomically record `elapsed_time_exceeded`, a failed
checkpoint, `budget.exceeded` and the FAILED transition. An outstanding invocation
gets one failed outcome and consumes one step; no new intent consumes no step.
Late results are discarded. The control exception carrying this committed state
is raised only after commit, so normal runtime callers receive the persisted
terminal state. Database errors/cancellation roll back and still propagate.
Ownership and revision checks precede expiry: an expired budget cannot let a stale
worker override another owner or a cancelled run.

Polling admits expired jobs even when retry eligibility is later, but never steals
a live lease. Validate retry history and move RETRYING → RUNNING/checkpoint before
normal expiry finalization; no new external operation is dispatched. If a process
stops between these commits, ordinary claimed recovery completes cleanup. Deadline
expiry takes precedence over step exhaustion or interrupted intent when observed.

## Limits and trade-offs

This is a durable execution deadline, not a hard real-time sandbox or queue SLA.
Database checks and external execution cannot be atomic: a process pause after the
last check can delay dispatch. Async timeouts require cooperative code; blocked
native code, an already-sent remote request or work in a thread cannot be forcibly
stopped. Late outcomes cannot succeed through the execution store. Clock changes
follow the database clock; local asyncio timeouts are a cooperative upper bound
for the remaining duration observed at the last check.

A crashed owner can delay terminal cleanup until its 660-second lease expires;
no lease stealing, heartbeat or background sweeper is added. Retry waits release
ownership and can be expired promptly by the next poll. Low-level repositories
remain trusted administrative APIs. Token/cost accounting, hosted idempotency,
workspace identity and mutation approval remain later slices.
