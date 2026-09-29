# ADR 0016: Durable repeated-tool limit

- Status: Accepted for Phase 5F
- Date: 2026-09-29

## Decision

Configuration/checkpoint version 7 requires `max_identical_tool_calls` (strict
integer 1–64), alongside version-6 budgets. It permits that many tool intents per
run for each pair of tool name and structurally equal JSON arguments. Matching
uses PostgreSQL JSONB equality: object key order is irrelevant, array order
matters, numbers such as 1 and 1.0 compare equal, and booleans remain distinct from
numbers. Decision summaries, model invocation IDs and intervening actions do not
reset the count. This is a run-wide exact-argument guard, not semantic loop inference.

Under the existing ownership/run-history locks, read the pinned configuration and
count matching `tool_calls` request records before creating the next intent. All
statuses count conservatively. Existing immutable invocation history is the
counter; no checkpoint counter, hash, migration or separate index is needed for
runs bounded to 64 invocation steps. Model retries do not create tool intents.

When the count is already at the limit, commit a
`runtime.repeated_tool_limit_exceeded` step/checkpoint, `budget.exceeded` with
`budget: identical_tool_calls`, and FAILED, then raise a committed-state control
exception for the runtime to return. No rejected tool intent or invocation step
is charged. The proposing model's successful response and token/cost usage remain
committed; the failed checkpoint retains `next_tool` and source as evidence.
Rollback leaves the prior checkpoint intact. Crash recovery reads the same history
and cannot reset the count. Cancellation/stale ownership and elapsed expiry retain
precedence; the core step limit can terminate first when it is already exhausted.

The new offline `fixture-loop-v1` repeats `fixture.info` with synthetic usage and
permits two identical calls. Its third proposal fails at five invocation steps
(three models, two tools). Older profiles retain their existing behavior.

## Limits

Different arguments or tool names have independent counts; alternating identical
calls still accumulate. Equivalent strings/paths or arguments after tool defaults
are not normalized. This can stop legitimate repeated polling, so operators must
choose the threshold deliberately. Existing step/token/cost/time limits bound
loops that vary their arguments. This does not enable tool retries or exactly-once
side effects. Low-level repositories remain trusted administrative interfaces.
Separate model/tool call budgets are the recommended next Phase 5 slice.
