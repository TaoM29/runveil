# Admission quarantine and operator release

Phase 5J applies automatic admission quarantine only to `fixture-calls-v1`, whether
selected through PostgreSQL polling or the SQS consumer. Migrate through `0008`.
Stop older worker/relay processes before relying on this policy: older application
versions do not apply admission selection/fencing checks. Mixed-version rolling
operation is not supported by this slice.
A configuration rejection happens before this execution attempt dispatches any
model/tool or writes runtime history. It is distinct from a failed invocation.

## What is counted

The execution store raises `ConfigurationRejected` for invalid pinned runtime
configuration/task construction, provider mismatch, absent required workspace
binding or a mismatch with the worker's expected configuration. For the calls
profile the worker records that rejection under its live claim, then propagates
the error. Existing CLI output remains `worker_failed` or `broker_failed`, exit 1.
Raw errors, task text and configuration are not stored in the admission audit.

Each committed rejection advances the admission revision and failure count,
clears the claim and starts a 30-second admission cooldown. The third rejection
sets `quarantined_at`; both execution selection and outbox publication stop selecting
that job, even after the cooldown ends. Duplicate/stale reports cannot increment
again. Existing deadlines continue aging; elapsed expiry does not override admission
cooldown/quarantine. A crash before the rejection transaction commits can leave
the original execution lease until expiry. The limit counts durable reports, not
process crashes that never record a rejection.

Quarantine leaves the run's lifecycle, runtime event tail, checkpoints, pending
intents and retry eligibility unchanged. Admission evidence uses a separate
append-only table keyed by run/admission revision, with `rejected`/`released`
actions, counts and database timestamps. Success does not reset prior rejection
counts; only explicit release resets them. Terminal runs are no longer selectable.

This classification excludes provider/tool failures, database errors, lost claims,
cancellation, unsupported checkpoint/history corruption, malformed broker messages,
repository capture errors and errors constructing the worker configuration before
claiming. Other worker profiles keep their existing behavior. Uncertain invocation
intent remains conservative interruption failure, not a retry opportunity.

## Inspect and repair

Use the existing local database setup and trusted operator credentials. These
commands make no AWS/provider/tool calls and print only bounded metadata:

```sh
uv run python -m runveil_worker.admission inspect --run-id UUID
```

The JSON contains `run_id`, `run_status`, `profile`, `failures`, `revision`,
`not_before` and nullable `quarantined_at`. It does not expose ownership tokens,
tasks or pinned configuration. Inspect authoritative run/history through the
existing persistence APIs when diagnosing the cause.

Restore a compatible worker implementation/configuration binding first. Then
release using the **revision just inspected** (example first quarantine: 3):

```sh
uv run python -m runveil_worker.admission release --run-id UUID --expected-revision 3
```

Release locks the run/job, requires a quarantined nonterminal executable run with
no live owner, checks that the admission revision still matches and compares the
stored configuration to the current supported `fixture-calls-v1` configuration.
It resets failures, clears quarantine/cooldown, increments revision and appends
release audit atomically. A second or stale release fails instead of clearing a
later quarantine. Invalid options exit 2; failed inspection/release prints only
`admission_failed` and exits 1. No free-text reason or credentials are accepted.

Release does not start execution or modify a pinned version, task, profile, queue
destination, deadline, checkpoint or invocation. Polling can select the job again;
the outbox will republish when its existing publication schedule/lease permits.
A resumed run may immediately expire under its original deadline, or fail its
original uncertain intent without replay.

A permanently invalid immutable version **cannot be repaired in place**. Create
a corrected version/new run using the trusted submission/persistence path and
cancel the old run through `RunRepository.transition(..., RunStatus.CANCELLED,
expected_revision=...)` under the normal revision/history rules. Do not edit SQL
configuration/history or clear quarantine by hand. Cancelled runs stay terminal;
release cannot revive them. This local operator interface is not authentication
or a multi-user administration UI.

## Broker and scope limits

Previously published messages for quarantined runs remain unacknowledged and
return `deferred`: acknowledgement still requires committed terminal state.
A relay already sending when quarantine commits may emit a stale notification;
claims refuse execution. Malformed messages require queue redrive/investigation;
no SQS dead-letter resources or general poison-message policy are provisioned.

Admission audit is not cleaned up and can grow across explicit release cycles.
Database owners remain trusted and can bypass application contracts. Downgrading
0008 removes the scheduling controls/audit and can re-enable quarantined jobs;
it is not a repair mechanism. Live AWS verification remains separate and opt-in.
See [ADR 0020](../adr/0020-worker-admission-quarantine.md) and
[the verification handoff](PHASE_5J.md).
