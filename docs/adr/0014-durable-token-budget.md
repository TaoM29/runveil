# ADR 0014: Durable reported-token budgets

- Status: Accepted for Phase 5D
- Date: 2026-09-29

## Decision

Configuration/checkpoint version 5 requires elapsed, input-token and output-token
limits. Existing profiles retain their semantics. The new offline
`fixture-token-v1` profile explicitly reports synthetic usage, including known
zero usage for its two deliberate pre-response failures.

Checkpoint accounting records completed model attempts, reported input/output
sums, unknown-usage attempt count and the latest attempt's nullable usage. Each
outcome and its accounting commit together using existing immutable checkpoints;
no new table or migration is necessary. Tool outcomes do not consume tokens.
Provider errors may carry normalized usage, never raw provider bodies. Missing
or partial usage retains known components and increments the unknown count.
Uncertain intent recovered after a crash is unknown, never zero and never replayed.

After each model attempt, reaching either configured limit terminates the run as
`token_limit_exceeded`; incomplete usage terminates as `token_usage_unknown`.
Unknown usage takes precedence over token exhaustion. Neither accepts a model
action or schedules a retry. Known usage from invalid actions is still counted.
Only known usage below both limits can proceed or retry under existing policy.
Elapsed expiry retains available normalized usage but discards late content;
expiry before dispatch or uncertain recovery conservatively records unknown usage.
Ownership/cancellation checks still take priority over all accounting writes.

## Limits and trade-offs

These are reported-usage stop thresholds, not a hard billing cap: one admitted
call can cross a threshold. No tokenizer, input estimate or invented reservation
is claimed. A hard pre-dispatch cap requires provider-specific input accounting
and output enforcement. Provider reports are trusted normalized evidence, not
independently audited billing. Unknown usage is a lower bound with explicit
uncertainty, never an exact total. Existing hosted adapters do not infer zero
usage from HTTP errors and are not enabled for durable worker replay.

Cost/pricing, provider idempotency and repository workspace identity remain
separate slices. Low-level repositories remain trusted administrative APIs.
