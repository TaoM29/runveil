# ADR 0019: Recurring outbox notifications with PostgreSQL ownership

- Status: Accepted for Phase 5I
- Date: 2026-09-29

## Decision

Add an opt-in SQS Standard notification path for the public `fixture-calls-v1`
profile. PostgreSQL remains the work queue and authority for profile, eligibility,
lease, cancellation, recovery and terminal state. Messages contain only a version
and run UUID; they never authorize arbitrary tasks, providers or repository roots.
Existing polling and submissions remain available and unchanged by default.

Migration 0007 adds one notification outbox row per opted-in job. Enrollment and
the immutable queue URL commit with run creation. Existing jobs are not backfilled.
The relay leases one eligible outbox row, sends outside the transaction, then
fences publication completion with its own token and database-clock expiry.
These publication leases are separate from execution leases. Unknown send outcomes
remain eligible after expiry; successful sends defer the next notification by
30 seconds rather than marking the row permanently delivered. Selection excludes
terminal, actively owned and not-yet-due jobs, using the existing deadline override.
Thus a lost/expired message or dead worker can be rediscovered without a new
execution write or a bespoke retry outbox hook. Publication races can send stale
notifications, which are harmless database hints. This trades extra messages for
simple recovery; this is not a production throughput design.

Consumers validate the bounded message envelope and match the enrolled queue and
fixed profile in PostgreSQL before attempting the existing worker claim. Only a
committed terminal run permits deletion using the received receipt handle.
Early/actively owned work, exceptions, invalid messages and unsupported enrollments
are left unacknowledged. A crash after terminal commit or delete failure causes
redelivery and terminal acknowledgement without repeating work. Invalid messages
require operator investigation/redrive; no automatic dead-letter setup is added.

Use boto3 for AWS signing/transport, with one SDK attempt and bounded connect/read
waits. CLI publication/consumption are explicit one-shot commands; no AWS calls
occur during ordinary polling, submission or tests. Operator queue URLs are pinned
to the commercial regional HTTPS SQS form, standard queues only, and the client
uses the region's explicit AWS endpoint. Credentials use the SDK chain and are not
stored or printed. No queue/IAM/Terraform resources are provisioned.

## Limits and sources

No exactly-once execution claim: execution fences protect database writes, not
external dispatch. The relay must keep running for recurring notifications; queue
visibility does not replace the 660-second database execution lease. Cooperative
thread cancellation cannot undo an SDK call. There is no outbox cleanup, broker
health endpoint, automatic poison-message quarantine or hosted/repository consumer.

AWS documents [at-least-once delivery](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/standard-queues-at-least-once-delivery.html),
[receipt-handle deletion](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/APIReference/API_DeleteMessage.html)
and [receive visibility](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/APIReference/API_ReceiveMessage.html).
Offline SDK stubs plus PostgreSQL tests establish local consistency; they do not
establish live AWS acceptance, IAM correctness or deployment readiness.
