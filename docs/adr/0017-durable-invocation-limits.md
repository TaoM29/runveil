# ADR 0017: Separate durable model/tool invocation limits

- Status: Accepted for Phase 5G
- Date: 2026-09-29

## Decision

Configuration/checkpoint version 8 requires `max_model_calls` and `max_tool_calls`
(strict integers 0–64), alongside version-7 budgets. Zero disables that invocation
kind. The existing `max_steps` remains a combined bound and need not equal their
sum. Older versions keep their behavior.

Before creating a model or tool intent, under the existing ownership/history
locks, read the pinned configuration and count all records of that kind in this
run. Failed, succeeded and uncertain requested attempts all count; retries are new
model attempts. Tool counts span names/arguments and are distinct from the
identical-tool limit. No mutable counter or migration is needed.

At capacity, atomically commit a `runtime.model_call_limit_exceeded` or
`runtime.tool_call_limit_exceeded` checkpoint, `budget.exceeded` with budget
`model_calls` or `tool_calls`, and FAILED. Raise the existing committed-state
exception only after commit. No blocked intent or invocation step is added;
existing token/cost usage and pending action evidence remain intact. Reaching the
limit is allowed: a successful final response at the limit still succeeds, and a
tool call may use remaining tool capacity after the last model call.

An otherwise eligible model retry with no model capacity left terminates in the
current outcome transaction without backoff or RETRYING. The invocation retains
its provider error; the checkpoint/run failure is `model_call_limit_exceeded`.
Existing non-retryable/provider, token/cost and exhausted retry/step policy errors
retain precedence. The store also refuses a schedule without remaining capacity.

Existing cancellation/ownership, elapsed expiry and core total-step checks retain
precedence at admission. Total tool capacity precedes identical-tool capacity.
Recovery resolves uncertain intent as `execution_interrupted` before any new
admission; it does not replay it or reinterpret it as a new budget failure.

The new offline `fixture-calls-v1` pins two model calls and one tool call, uses
known synthetic usage/pricing without deliberate retries, and succeeds exactly at
both limits in three steps. No additional execution capabilities are enabled.

## Limits and next work

These are committed-intent limits, not a guarantee about provider-side internal
retries, a paused old process, billing, or exactly-once side effects. The current
worker still executes only fixed offline profiles. Trusted administrative
repositories remain below runtime admission policy.

Next, establish a pinned repository workspace/implementation identity before
exposing durable read-only repository recovery. Broker consistency and hosted
retry/idempotency remain open Phase 5 work; mutation/approval stay in later phases.
