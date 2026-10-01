# ADR 0026: Read-only durable run trace

- Status: Accepted for Phase 7A
- Date: 2026-10-01

## Decision

Start Phase 7 with a bounded authenticated trace API over PostgreSQL evidence.
`GET /runs/{run_id}/trace` uses a separate `RUNVEIL_TRACE_TOKEN` capability;
it does not authorize approval decisions. No run listing or execution endpoint
is added. The local-only, shared-operator restrictions of ADR 0024 still apply.

Each request uses a REPEATABLE READ, READ ONLY transaction, without row locks.
Run state, latest checkpoint accounting, approval state, invocation metadata and
ordered events therefore share one committed snapshot without blocking workers.
An event watermark identifies that snapshot. Subsequent pages must supply it as
`expected_sequence`; changed history returns 409 and requires restarting inspection.
This deliberately favors coherent reads over continuously streaming a busy run.

Return explicitly selected metadata, never raw event payloads, model messages,
arguments, tool outputs, patch contents, workspace paths or provider responses.
The final summary is an explicitly sensitive operator field, bounded to 4096
characters with a truncation flag; artifact paths are omitted. SQL projections
avoid loading content-bearing JSON documents. Unknown/legacy checkpoint accounting
is unavailable, never fabricated as zero. Version 5+ token totals and version 6+
cost estimates come from the latest checkpoint, retaining unknown-attempt counts.
Cost remains integer nano-USD under the pinned tariff, not a bill. Intent counts
include unresolved calls. Retry links identify actual retry requests, separately
from the checkpoint count of scheduled retries.

Invocation duration measures persisted request-to-outcome wall time, including
storage/recovery delays, not provider latency or CPU time. Unresolved durations
are null. Run elapsed time includes approval waits, retry delays and downtime.
Sequence, not timestamps, orders events. Approval status is descriptive and never
an authorization decision. Migration baselines remain explicitly incomplete.

## Scope and consequences

No runtime, schema, dependency or existing authorization behavior changes.
Telemetry export, OpenTelemetry spans, structured logs, and the trace UI remain
later Phase 7 slices. Persisted evidence is the UI's authority; future best-effort
telemetry must not replace it or enter durability/authorization decisions.
Responses are no-store, requests bounded by a five-second timeout, pages by 100
events and serialized responses by 512 KiB. Errors are fixed and non-reflecting.
This is not a public or multi-tenant API, a redaction service, or a retention policy.
