# Durable fixture worker

Phase 5A introduced `fixture-v1`; Phase 5B adds the opt-in `fixture-retry-v1`
profile. Both use the built-in public fixture, never repository files, hosted
models, arbitrary tools or secrets.
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
withdrawing it prevents dispatch. The CLI grants it only to the new offline profile. A hosted HTTP
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

General/hosted retries and token/cost/wall-time budgets are deferred. Existing
step limits and cooperative per-call deadlines remain active across recovery.
Repository and hosted-provider recovery need explicit workspace/implementation
identity and attempt/idempotency policies before being exposed by a worker.
