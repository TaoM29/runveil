# Durable offline worker

The fixture profiles are `fixture-v1`, `fixture-retry-v1`, `fixture-budget-v1`, `fixture-token-v1`, `fixture-cost-v1`, `fixture-loop-v1` and (Phase 5G) `fixture-calls-v1`. All use the built-in public fixture, never repository files,
hosted models, arbitrary tools or secrets.
See [ADR 0011](../adr/0011-durable-fixture-worker.md) for ownership and recovery rules.

## Run locally

Complete the [development setup](DEVELOPMENT.md#local-quickstart), then:

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

## Repeated-tool limit

Submit and process `--profile fixture-loop-v1`. This intentionally failing offline
demo proposes `fixture.info` repeatedly, with the same synthetic usage/prices as
the cost fixture and no scheduled retries. It permits two identical tool calls;
the third proposal produces `status=FAILED steps=5 retries=0` and `work --once`
exits 1. The checkpoint records `repeated_tool_limit_exceeded`, three model
attempts, two tool intents, 30 input/15 output tokens and 75,000 nano-USD. Repeat
delivery returns `no_eligible_work`. The total step limit is eight, leaving room
for this guard to act first.

Version 7 requires `max_identical_tool_calls` (strict integer 1–64), plus version-6
budgets. The limit counts committed tool intents across the entire run, including
all statuses, for the same tool name and structurally equal JSON arguments. The
store reads the immutable configuration; a caller cannot relax the bound by
passing a different configuration to `request`.

Object key order does not matter, array order does, JSON numbers 1 and 1.0 match,
and true differs from 1. This is PostgreSQL JSONB equality, not equality after
applying tool defaults, path normalization or semantic interpretation. Decision
summaries and model IDs do not participate. Alternating other actions does not
reset a pair's count; different tool names or arguments have separate counts.

Before admitting another matching intent at the limit, the store atomically
writes `runtime.repeated_tool_limit_exceeded`, a checkpoint, `budget.exceeded`
(`budget: identical_tool_calls`) and FAILED. No new tool intent is created or
dispatched, and `steps_used` does not increase. The proposing model response and
its usage remain committed; `next_tool` and source identify the blocked proposal.
Recovery at that model checkpoint reaches the same decision. Rollback preserves
the previous checkpoint; stale owners/cancelled runs cannot write budget failure.
Elapsed expiry takes precedence when observed at the store boundary; an already
exhausted core step budget can terminate first.

The guard may stop legitimate repeated polling. Choose the limit deliberately.
Other budgets still bound loops that vary arguments. This adds neither tool
retries nor exactly-once side effects, and existing profiles keep their behavior.
See [ADR 0016](../adr/0016-durable-repeated-tool-limit.md).

## Separate model and tool call limits

Use `--profile fixture-calls-v1` on both `submit` and `work`. This fixed profile
uses known synthetic token usage/pricing with no deliberate failures or scheduled
retries. It pins two model calls, one tool call, eight total steps and two identical
tool calls. A normal model → tool → finish run succeeds at `steps=3 retries=0`,
exactly at the two independent call limits. It retains 20 input/10 output tokens
and a 50,000 nano-USD cost estimate.

Version 8 requires `max_model_calls` and `max_tool_calls`, strict integers from
0 to 64, alongside the version-7 budgets. Zero disables that invocation kind.
Neither sum nor individual cap replaces `max_steps`; whichever active boundary
is reached first applies. Older profiles have no separate call caps.

Admission reads the immutable configuration and counts committed records of the
requested kind across the run under the existing ownership/history locks. All
statuses count: completed success, failed attempts and uncertain requested intent.
Each model retry consumes another model slot; tool capacity spans all tool names
and arguments. A caller cannot raise the bound through the per-request config.

If no capacity remains, atomically checkpoint `model_call_limit_exceeded` or
`tool_call_limit_exceeded`, record `budget.exceeded` (`model_calls` or `tool_calls`)
and fail the run. No new intent, dispatch, usage or invocation step is charged.
A previously committed proposing model response and pending tool evidence remain
in history. A successful finish at the limit is accepted; a last model call can
still be followed by a tool within its own limit.

An otherwise eligible retry with no model capacity remaining fails in its outcome
transaction, without scheduling a retry or waiting for backoff. The invocation
retains the provider error and usage; the checkpoint records
`model_call_limit_exceeded`. Non-retryable/provider errors and already-exhausted
retry/step policy retain their existing behavior. The store rejects attempts to
schedule a retry at capacity as well.

Recovery never resets these counts. Unresolved intent still fails once as
`execution_interrupted`, retaining its original record; it is not replayed or
reclassified as an admission failure. Ownership/cancellation, observed elapsed
expiry and the core total-step check keep their existing precedence. Total tool
capacity is checked before the identical-tool limit.

These limits cover durable intents, not a provider's internal attempts or
exactly-once execution outside the database. No new migration or counters are
needed. See [ADR 0017](../adr/0017-durable-invocation-limits.md).

## Pinned repository recovery

Phase 5H adds `repository-read-v1`, a fixed offline demonstration using explicitly
selected repository text. Vet the files before submission: captured text is not
secret-scanned, and read results enter durable model/tool history. Use a stable
local directory and supply the same root and exact allowlist on both commands:

```sh
uv run python -m runveil_worker submit --profile repository-read-v1 \
  --repository-root /absolute/approved/checkout --file src/example.py
uv run python -m runveil_worker work --profile repository-read-v1 --once --run-id UUID \
  --repository-root /absolute/approved/checkout --file src/example.py
```

Repeat `--file` for each selected file. Root/files are mandatory; repository work
also requires `--once --run-id`. These flags are rejected for fixture profiles.
The provider requests only the first 4096-character excerpt of the first sorted
file, then emits a static finish summary. It does not analyze code or call a hosted
model. A successful run consumes two model calls/one tool call, three steps,
20 input/10 output synthetic tokens and 50,000 nano-USD. It inherits the calls
profile's 30-second budget, 100-token input/output limits, 100,000 nano-USD cap,
eight-step/two-identical-call limits and no retries.

Submission and each work invocation capture the complete allowlist into immutable
memory: up to 128 paths, 64 KiB per file and 1 MiB total, UTF-8 without NUL, using
all existing [repository boundaries](REPOSITORY_TOOLS.md). Version 9 pins three
SHA-256 fingerprints: root path/device/inode, selected paths/content and covered
tool source/Python/Pydantic versions. Recovery reconstructs the snapshot and
compares the entire configuration before dispatch or history writes. A moved or
replaced root, changed allowlist/selected bytes, or covered implementation change
prints `worker_failed`; the claim can remain until lease expiry. Do not rebind the
run to new content. Failed capture occurs before claiming; even a duplicate work
invocation must first capture a valid binding.

An active snapshot ignores later file edits. Recovery needs identical local
contents and root identity; there is no durable content archive. Capture is not
an atomic Git revision. This is trusted application configuration, not protection
against malicious native code. Clean checkpoints recover before/after a read;
uncertain intents still fail without replay. See
[ADR 0018](../adr/0018-pinned-repository-recovery.md).

## Process-death acceptance

Run `uv run python scripts/phase5_acceptance.py` with `RUNVEIL_TEST_DATABASE_URL`
set to the test admin database. It uses a separate disposable database, actual
SIGKILL/fresh worker processes, and offline SQS wire stubs. It verifies checkpoint
continuation and terminal duplicate acknowledgement, plus uncertain-intent failure
without replay. The harness advances lease expiry only after its child has died;
production lease/deadline policy is unchanged. See [Phase 5 acceptance](PHASE_5.md).

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
  until expiry, except for the calls profile's explicit configuration rejections.
  Phase 5J records those under the live claim, clears ownership and applies a
  30-second cooldown; the third rejection quarantines the job. See
  [admission inspection/release](ADMISSION.md). No general automatic repair is added.

The CLI emits IDs/status/counts and fixed error codes only; it suppresses raw
exceptions. Stored tasks/context are not redacted. Enroll only approved content.
Version-1 runtime checkpoints remain readable through `load_runtime_state`, but
are not resumable. Migration 0004 does not enroll or reinterpret existing runs.

## Limits

The default transport remains PostgreSQL polling. Phase 5I adds a separate opt-in
[SQS notification adapter](BROKER.md) for `fixture-calls-v1`; neither path is a
production scheduler.
Database writes are fenced; external execution cannot be made atomic with a claim.
A paused old process may still execute its read-only operation after losing ownership,
but cannot commit its result. This is not exactly-once execution.

General/hosted retries and richer billing models are deferred. Existing
step limits and cooperative per-call deadlines remain active across recovery.
General repository agents and hosted-provider recovery remain deferred; hosted
retries need an explicit attempt/idempotency policy. The repository profile above
is a bounded offline demonstration, not general autonomous repository work.

## Repository approval review

Phase 6B adds a separate `runveil_worker.review_worker` CLI for the offline
`repository-review-v1` profile. It uses normal claims, budgets and snapshot identity
with one durable human review pause. Waiting releases ownership and excludes the
job from selection. Approving checkpoints a RUNNING continuation; a fresh worker
must match the workspace before any further dispatch. Rejection is terminal.
No file is written. This profile is not supported by the fixture worker CLI or
SQS consumer. See [approval operations](APPROVALS.md#workspace-bound-worker-review-phase-6b).
