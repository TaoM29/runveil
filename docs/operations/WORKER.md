# Durable fixture worker

The offline profiles are `fixture-v1`, `fixture-retry-v1`, `fixture-budget-v1`, `fixture-token-v1` and (Phase 5E) `fixture-cost-v1`. All use the built-in public fixture, never repository files,
hosted models, arbitrary tools or secrets.
See [ADR 0011](../adr/0011-durable-fixture-worker.md) for ownership and recovery rules.

## Run locally

Complete the README dependency/database setup, then:

```sh
uv sync --locked --all-packages
uv run alembic upgrade head
uv run python -m runveil_worker submit
uv run python -m runveil_worker work --once
```

`submit` atomically creates a new immutable agent version, run and enrolled job,
then prints its run ID. Each submission deliberately creates a new run. `work
--once` selects at most one eligible job and exits; `work --once --run-id UUID`
selects a specific enrolled run. Repeated delivery of the same ID does not execute
an actively owned or terminal run. A failed run makes `--once` exit with status 1. An empty selection prints `no_eligible_work`.
Without `--once`, the worker polls every second until interrupted. Multiple worker
processes may share the database. Selection skips locked run rows.

A normal run prints `status=SUCCEEDED steps=3`: model → fixture → model finish.
The task, execution profile and configuration are durable. Provider response
selection uses persisted context, so restarting a process does not reset an
in-memory script index. Profile semantics are versioned in application code;
change the profile ID when changing those semantics.

## Persisted model retries

After migration 0005, submit and process the new profile explicitly:

```sh
uv run python -m runveil_worker submit --profile fixture-retry-v1
uv run python -m runveil_worker work --once --profile fixture-retry-v1
```

The first two attempts deliberately return a known pre-response rate-limit error.
They print `status=RETRYING`, with persisted step/retry counts, and exit successfully.
Repeat the work command after the first one-second delay and then the two-second
delay; the third eligible invocation finishes with `status=SUCCEEDED steps=5
retries=2`. Early delivery prints `no_eligible_work`. Alternatively, omit `--once`
to poll continuously; interrupt the process when done. A worker selects only its
chosen profile, which defaults to the unchanged `fixture-v1`.

The new profile pins configuration version 3, a run-wide limit of two retries,
one-second base backoff and five invocation steps. Core policy supports at most
three retries and a 1–60 second base, with exponential delay capped by those bounds
at 240 seconds. Successful operations do not reset the retry count. Both pinned
configuration and `execute(allow_model_retries=True)` are required; the latter is
a trusted operator assertion that this provider's explicit rate-limit failure is
safe to repeat. The grant is checked again before resuming a scheduled retry;
withdrawing it prevents dispatch. The CLI grants it only to the retry, budget, token and cost fixture profiles. A hosted HTTP
error code alone does not establish safe replay.

Scheduling atomically retains the failed model invocation, checkpoints the count,
records `retry.scheduled` with source ID and database-clock eligibility, transitions
to RETRYING and releases the lease. A different process may claim it when due.
Resumption checks the schedule and source, transitions back to RUNNING and saves a
new checkpoint. The new invocation has a distinct ID and the same request; its
`model.requested` event links the failed predecessor through `retry_of`. The retry
counter and prior failed attempts remain in history after eventual success.

Only explicit rate-limit failures are eligible. Timeouts, unavailable providers,
invalid responses, unexpected exceptions, tool errors and uncertain dispatch fail
without retry. When the retry or step limit is reached, the last provider error
is terminal and no further schedule is created. Every attempt consumes one step.
A crash before the scheduling transaction commits leaves uncertain intent, which
still fails as `execution_interrupted`; a crash after commit preserves the schedule.
Cancellation during backoff prevents further execution. See [ADR 0012](../adr/0012-persisted-model-retries.md).

## Durable elapsed-time budget

After migration 0006, select the budgeted profile explicitly:

```sh
uv run python -m runveil_worker submit --profile fixture-budget-v1
uv run python -m runveil_worker work --once --profile fixture-budget-v1
```

This profile uses the same two known failures and retry delays, with a **30-second
execution budget**. Repeat `work --once` after the one-/two-second backoffs within
that budget, or omit `--once` to poll continuously. A normal run succeeds at five
steps/two retries. `fixture-v1` and `fixture-retry-v1` retain their existing behavior.

Configuration/checkpoint version 4 requires `max_elapsed_seconds` (integer 1–86400).
The execution store persists `worker_jobs.deadline_at` as the run's first
`started_at` plus that limit, in the start transaction. Initial queue time does not
count; every later retry wait, call and process outage does. An assigned deadline
cannot be changed or cleared. Recovery checks it against pinned configuration and
the original start time rather than extending it.

The runtime checks database time immediately before dispatch, after each call and
at every execution-store write boundary. Cooperative calls use the smaller of the
remaining elapsed duration and their own timeout. Persisted model requests keep
their original per-call timeout so retry identity remains unchanged.

At or after the deadline, atomically write `elapsed_time_exceeded`, a failed
checkpoint, `budget.exceeded` and FAILED. A pending invocation receives a failed
outcome and counts once; no new intent means no additional consumed step. Late
results are discarded. Expiry takes precedence over step-limit or interrupted-
intent failure when observed. Existing ownership and history checks take priority:
an expired budget cannot authorize a stale owner or override cancellation.

An expired retry becomes selectable even before its retry eligibility time. Its
validated continuation transitions through RUNNING before expiry finalization;
no new model/tool operation is dispatched. A crash between those transactions is
recoverable. Polling never steals an active lease, so cleanup after a worker crash
can wait up to the existing lease expiry. There is no background sweeper.

These are database-clock admission checks and cooperative timeouts, not a hard
real-time sandbox. A process can pause between a check and dispatch; blocked
native code or an already-sent remote request cannot be forcibly stopped. Results
presented to the store after expiry cannot succeed. See
[ADR 0013](../adr/0013-durable-elapsed-budget.md).

## Durable reported-token budgets

Select `--profile fixture-token-v1` on both `submit` and `work`. Like the elapsed
profile, it has two delayed retries and a 30-second deadline. It reports synthetic
zero usage for the deliberate failures, then 10 input/5 output tokens per model
response: successful completion totals 20 input/10 output, four model attempts
and one tool call. These numbers demonstrate accounting, not real tokenization.

Version 5 requires `max_input_tokens` and `max_total_output_tokens` (strict integers
1–1,000,000,000), in addition to the elapsed limit. The fixture pins both to 100.
`max_output_tokens` remains the separate per-request generation parameter.
After every model attempt, reaching or exceeding either cumulative threshold
fails with `token_limit_exceeded` and `budget.exceeded`. Missing either usage
component fails with `token_usage_unknown` and `budget.unknown`. Unknown takes
precedence if both conditions apply. The model action is discarded and no tool or
retry follows, including when the response was a finish action.

Checkpoints retain `tokens`: completed model attempts, known input/output sums,
unknown attempt count and nullable `last_usage`. Known components of partial usage
remain visible; totals with unknown attempts are lower bounds. Provider errors
can supply normalized usage, but missing usage is never inferred to mean zero.
Invalid actions still consume their reported usage. Known rate-limit failures
below both thresholds may retry under the existing grant and count policy.

Outcome, accounting, budget event and terminal transition are one transaction.
Recovery verifies model-attempt counts against history. Unresolved model intent
records one unknown attempt with `execution_interrupted`; unresolved tools do not
change model accounting. Elapsed expiry retains usage supplied with an outcome
but discards its content. Before-dispatch expiry conservatively counts committed
model intent as unknown. Cancellation or stale ownership prevents the whole write.

These limits stop subsequent work based on reported usage. One model call can
cross a threshold; this is not a pre-dispatch token or monetary cap. No input-token
estimation or provider-specific output guarantee is implied. Existing profiles
retain their behavior and do not backfill token accounting. See
[ADR 0014](../adr/0014-durable-token-budget.md).

## Pinned pricing and cost limits

Use `--profile fixture-cost-v1` on both `submit` and `work`. It retains the token
fixture's two known zero-usage failures, elapsed/token limits and retry delays.
Its immutable `fixture-linear-usd-v1` tariff charges synthetic 1,250 nano-USD per
input token and 2,500 per output token. The run limit is 100,000 nano-USD. A normal
run succeeds after five steps/two retries, with 20 input/10 output tokens and an
estimated 50,000 nano-USD (USD 0.00005). These are fixture numbers, not live prices.

Configuration version 6 requires:

- `pricing`: `price_id`, matching `provider` and `model`, `currency: "USD"`,
  `input_nanousd_per_token` and `output_nanousd_per_token` (strict integers 0–10^9).
- `max_cost_nanousd`: a strict positive integer up to 10^15, plus the existing
  elapsed and input/output token limits.

One nano-USD is USD 0.000000001. Integer multiplication/summation avoids floating
point and per-attempt rounding. Rates bind to the configured request model,
including an alias, rather than a mutable price registry or a response model name.
The full pinned rate snapshot is authoritative; price IDs are audit labels.
Changing rates requires a new agent version/profile. Missing/unknown rates,
unsupported currency, fractional rates or mismatched identities reject the
configuration before execution (`worker_failed` through the CLI); no price is
inferred and no attempt is dispatched. Zero rates must be explicit.

Checkpoints store `cost.known_nanousd` and `cost.unknown_attempts`. Known token
components contribute to cost even for rejected actions, failed calls or partial
usage. Unknown consumption is never presented as an exact zero, including with
zero rates. Token unknown/limit errors take precedence over cost-limit errors;
interruption/elapsed expiry retain their existing precedence and cost evidence.

At or above the threshold, reject the response action (including finish), persist
`cost_limit_exceeded`, a `budget.exceeded` event with `budget: "cost"` and FAILED
atomically. No retry follows. Recovery recomputes cost against pinned pricing and
usage; normal and retry outcome boundaries validate the same relationship. Tools
do not incur modeled cost. No new migration is required.

This supports linear input/output estimates only. It cannot express cache tiers,
request fees, reasoning-token surcharges, taxes or other billing dimensions.
Operators must select a tariff that fits the normalized usage contract. It is not
invoice reconciliation, and one admitted call may exceed the stop threshold.
Existing profiles retain their semantics and have `cost: null`, not a claim of
free execution. See [ADR 0015](../adr/0015-pinned-cost-budget.md).

## Ownership and restart

Each claim lasts 660 seconds according to the database clock and is renewed at
committed runtime boundaries. There is no heartbeat or shutdown lease release.
The lease exceeds the maximum supported 600-second model call; this worker uses
only immediate offline operations. After process death, restart the worker and
wait for expiry. Do not manually clear a live worker's lease in normal operation.

Every execution-store write locks the run, validates the live ownership token,
and renews the lease in the same transaction. Expired or replaced workers cannot
persist late results. An ordinary unclaimed execution store cannot operate on an
enrolled run. Trusted low-level repositories remain available for administrative
lifecycle operations, including cancellation. Tokens are never printed.

- After a clean checkpoint, resume the next operation. Committed model and tool
  outcomes are retained; the model's next tool action and provenance are stored.
- After a request intent with no outcome, record `execution_interrupted` and fail
  the run atomically. The uncertain invocation consumes one step and is never
  replayed. Even a crash immediately before dispatch takes this conservative path.
- After a terminal commit, repeated delivery does nothing.
- Unknown checkpoint versions, inconsistent history, or configuration/profile
  mismatch stop the worker with `worker_failed` and a nonzero exit. No provider
  dispatch follows. Investigate the stored history/configuration; the lease remains
  until expiry. There is no poison-job quarantine or automatic repair yet.

The CLI emits IDs/status/counts and fixed error codes only; it suppresses raw
exceptions. Stored tasks/context are not redacted. Enroll only approved content.
Version-1 runtime checkpoints remain readable through `load_runtime_state`, but
are not resumable. Migration 0004 does not enroll or reinterpret existing runs.

## Limits

This is a local PostgreSQL worker, not an SQS adapter or a production scheduler.
Database writes are fenced; external execution cannot be made atomic with a claim.
A paused old process may still execute its pure fixture after losing ownership,
but cannot commit its result. This is not exactly-once execution.

General/hosted retries and richer billing models are deferred. Existing
step limits and cooperative per-call deadlines remain active across recovery.
Repository and hosted-provider recovery need explicit workspace/implementation
identity and attempt/idempotency policies before being exposed by a worker.
