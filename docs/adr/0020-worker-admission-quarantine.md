# ADR 0020: Bounded configuration rejection quarantine

- Status: Accepted for Phase 5J
- Date: 2026-09-29

## Decision

Add durable admission quarantine for `fixture-calls-v1`, shared by polling and the
SQS consumer. Only explicit configuration validation/binding rejections raised by
execution-store start are classified. Use a distinct `ConfigurationRejected`
exception (a ValueError subtype), not a broad exception catch. Provider/tool
failures, database errors, lost ownership, cancellation, malformed broker messages,
checkpoint/history corruption and repository capture errors are not classified.
Other fixture/repository profiles retain their current failure behavior.

Migration 0008 adds job rejection count, admission revision, admission eligibility
and quarantine timestamp. A worker records a rejection under its live execution
claim, in run/job lock order, only for a nonterminal run. Each record increments
count/revision, appends immutable admission audit evidence, and clears ownership.
A 30-second admission cooldown precedes each subsequent claim. The third rejection
quarantines the job: claims and recurring outbox publication exclude it. Admission
cooldown/quarantine are not bypassed by elapsed expiry. Existing deadlines continue
to age; release never extends them. A stale or duplicate failure report cannot count
again after ownership is cleared. A crash before recording leaves the old lease
until expiry and may require another admission attempt; the bound covers committed
rejections, not unobserved process failures.

Quarantine is scheduling state, not a run lifecycle transition. Runtime events,
checkpoints, invocation records and retry schedules are untouched. Audit records
use a separate append-only table so they cannot invalidate recovery's event tail.
Only fixed action names, counts/revisions and timestamps are recorded, without raw
exception/task/configuration/credential content. No schema change in core runtime.

An explicit local operator command inspects bounded metadata or releases a job.
Release requires quarantine, no live owner, a nonterminal run, the observed admission
revision and a matching supported immutable configuration. It resets the count,
advances revision and audits release atomically. It does not modify configuration,
profile, destination, history or invocation state. Restore a compatible worker
binding first; a permanently invalid version requires a replacement version/run
and administrative cancellation of the old run, not in-place repair. The database
credential is the existing trusted operator boundary; no authentication UI or
arbitrary operator notes are introduced.

Already-published notifications for quarantined jobs remain unacknowledged under
the terminal-only rule. Relay selections racing quarantine may emit a stale hint;
execution claims still refuse it. Operator release restores selection, and the
existing outbox republishes without rewriting its state. Malformed queue messages
still require queue redrive/investigation; this is not an automatic SQS DLQ policy.

## Limits

Automatic classification is deliberately narrow and profile-specific. Revision
checks prevent stale release requests from clearing a later quarantine cycle.
Successful admission does not erase prior rejections; they accumulate until explicit
release (or terminal completion makes scheduling irrelevant). Audit growth across
operator releases is not capped or cleaned up. Live AWS acceptance and production
operations remain separate work. Downgrading 0008 removes quarantine/audit and can
make blocked jobs eligible again; it is not an operational repair procedure.
