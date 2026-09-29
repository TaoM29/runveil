# SQS notification operations

Phase 5I adds an opt-in SQS Standard path for the fixed public `fixture-calls-v1`
profile. PostgreSQL remains authoritative. The model/tool workflow is offline;
**publish/work commands call AWS**. Local checks use SDK stubs, not AWS credentials,
paid services or queue emulators. No live AWS acceptance has been performed.

## Commands and prerequisites

Install locked dependencies and migrate through `0007` using the README setup.
A queue must already exist. This slice does not create queues, IAM roles, redrive
policies or infrastructure. Only commercial regional HTTPS URLs are accepted;
FIFO, custom endpoints, China/GovCloud and queue URL query parameters are unsupported.
Credentials come from the normal AWS SDK chain and are never persisted or printed.
Use an explicitly approved account/queue and grant the relay `sqs:SendMessage`,
and the consumer `sqs:ReceiveMessage`/`sqs:DeleteMessage`, on that queue.

Submission below writes only PostgreSQL and makes no AWS call. Substitute an
operator-approved queue URL; its region determines the explicit SDK endpoint:

```sh
uv run python -m runveil_worker.sqs submit \
  --queue-url https://sqs.us-east-1.amazonaws.com/123456789012/approved-queue
```

For an explicitly authorized live check, the following send and receive/delete
messages in that queue:

```sh
uv run python -m runveil_worker.sqs publish \
  --queue-url https://sqs.us-east-1.amazonaws.com/123456789012/approved-queue
uv run python -m runveil_worker.sqs work \
  --queue-url https://sqs.us-east-1.amazonaws.com/123456789012/approved-queue
```

Every command is one-shot: publish leases/sends at most one eligible notification;
work receives at most one message with a ten-second long poll and 30-second
visibility. Run relay and consumers repeatedly under operator supervision for
ongoing delivery. No daemon, automatic process supervision or visibility heartbeat
is included. SDK connect/read timeouts are 3/25 seconds with one attempt; failures
print `broker_failed` and exit 1 without raw AWS/database details. Cancellation
exits 130. Background SDK threads may finish after cancellation.

Submission prints the run UUID. Publication prints `published` or
`no_eligible_work`. Consumption prints `no_message`, `deferred`, `rejected` (exit 1),
or `acknowledged`. Acknowledged means terminal state and successful delete request,
not necessarily a successful run; inspect PostgreSQL for the run outcome. Receipt
handles and message bodies are not logged. There is no public broker HTTP endpoint.

## Consistency and recovery

Run, immutable version, job and destination-specific outbox enrollment commit in
one transaction. A failed transaction publishes nothing. Existing polling jobs
are not adopted. There is one outbox row per opted-in job; changing its destination
requires a new run. Python enrollment APIs are trusted administrative code.

The relay uses a separate 60-second database publication lease with a random token.
Network sends occur outside transactions. Failed/unknown sends leave the lease
until expiry; a stale publisher cannot mark completion. A successful send clears
that lease and sets the next publication time 30 seconds ahead. The row stays:
publication repeats while the run is eligible and unowned until it is terminal.
No permanent sent flag can strand work after message loss/retention expiry.
Eligibility uses the job's due time/deadline override and execution lease. A
selection race can send a stale notification, which remains only a hint.
Phase 5J also excludes admission cooldown/quarantine from publication and execution
claims. Quarantined redeliveries return `deferred` and remain unacknowledged;
verified operator release restores eligibility. See [admission operations](ADMISSION.md).

Messages contain only `schema_version: 1` and `run_id`; bodies are limited to
1024 UTF-8 bytes. Unknown/malformed envelopes and jobs outside the pinned queue
and fixed profile are rejected without execution or deletion. The database stores
the task/configuration, never trusting message-supplied bindings. Even a guessed
valid run ID cannot select another queue's enrollment.

The consumer runs the existing claim/checkpoint path. Busy or early jobs remain
unacknowledged. Only committed SUCCEEDED/FAILED/CANCELLED permits deletion with the
current receipt handle. A crash after terminal commit, delete failure or duplicate
message leads to another terminal acknowledgement without repeating execution.
Errors during execution leave the message and existing lease for recovery. An
expired execution lease is rediscovered by both redelivery and recurring outbox
publication. Uncertain model/tool intent still fails conservatively without replay.

PostgreSQL polling can process these runs too, for example
`uv run python -m runveil_worker work --once --profile fixture-calls-v1 --run-id UUID`.
Queue visibility is not execution ownership; the existing 660-second lease and
transactional fences govern writes. There is no exactly-once external execution.

## Limits and verification

Recurring publication deliberately trades additional messages/cost for a simple
recovery mechanism. Malformed messages stay unacknowledged; configure redrive and
investigate them operationally. Repeated explicit configuration rejections for
the calls profile now enter durable quarantine after three recorded failures.
Unclassified failures, other profiles and malformed messages are not automatically
quarantined. No outbox cleanup, metrics,
readiness probe or deployment throughput claim is provided. Other worker profiles,
including repository and hosted execution, are not accepted by this consumer.

Offline checks:

```sh
RUNVEIL_TEST_DATABASE_URL=postgresql+psycopg://runveil:runveil-local-only@127.0.0.1:5432/postgres \
  uv run pytest packages/persistence/tests/test_broker.py
```

These cover the SDK wire calls together with PostgreSQL rollback, migration,
publication ownership, duplicates and terminal acknowledgement. They do not verify
live IAM, credentials, queue configuration or AWS delivery timing. See
[ADR 0019](../adr/0019-sqs-notification-outbox.md) and [the handoff](PHASE_5I.md).
