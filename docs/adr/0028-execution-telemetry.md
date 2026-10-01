# ADR 0028: Best-effort execution telemetry

- Status: Accepted for Phase 7C
- Date: 2026-10-01

## Decision

Instrument the existing core execute call, model attempt and read-tool dispatch
with the OpenTelemetry API. The worker owns SDK configuration; the core never
imports the SDK, exporter, environment or logging configuration. Explicit scoped
tracer injection defaults to disabled. Worker command entry points opt in using
`RUNVEIL_TELEMETRY=json`; no global provider, automatic instrumentation, ambient
trace/baggage propagation or environment-selected network exporter is installed.

Each execute invocation starts a fresh root `agent.execute` span. Resumed/retried
executions correlate by durable run ID, not fabricated continuous spans across
process death or approval waits. Child spans identify committed invocation intent
and its request event sequence. Span timing is local observed elapsed time, not
proof of a committed outcome; durable trace timing keeps its existing meaning.
Approved patch dispatch is observed around the existing fenced store call, never
inside its database/filesystem critical section. No telemetry can authorize work,
retry, replay, alter a transaction or substitute for persisted history.

Root completion reports only finite fixed outcome labels and numeric checkpoint
accounting (including unknown usage/cost), not final content. Child metadata is
limited to durable IDs, event positions and fixed classifications. Model names,
provider labels, arbitrary tool names, prompts, responses, tool arguments/results,
workspace paths, credentials, raw exceptions and exception stack traces are omitted.
No SDK exception recording is used. Tool names are not required for correlation:
the durable invocation ID resolves the exact call in the authenticated trace API.

The worker exports completed spans as bounded structured JSON records on stderr,
including OTel trace/span/parent IDs and timestamps. A bounded SDK batch processor
keeps output I/O outside the execution path. Export is best effort: saturation,
process death or output failure may lose telemetry. The JSON exporter catches
output errors without logging their exception contents. No output file, collector,
network destination, credential or deployment is provisioned by this slice.

## Consequences

Supporting OpenTelemetry API/SDK dependencies are added and locked. Runtime policy,
checkpoint schemas, persisted events, authenticated read-only API/UI and mutation
boundaries remain unchanged. No metrics, distributed cross-process propagation,
API auto-instrumentation or telemetry UI is claimed. The established trace UI
continues to consume durable evidence only. Telemetry helper failures must preserve
original exceptions/cancellation and never turn provider success into retryable
failure; focused tests verify this and reconcile emitted IDs/accounting with the DB.

The CLI shuts the SDK down after execution and DB cleanup; a stalled sink may
delay process exit by the SDK's default bounded join (up to 30 seconds). The SDK
export timeout does not forcibly interrupt blocked writes. No synchronous force
flush is inserted into execution. Arbitrary custom tracers remain trusted
application configuration, not a hard time-isolation boundary.

Claim/admission, operator decisions and uncertain-patch cleanup outside core execute
are deliberately omitted. Root completion precedes worker finalization, so emitted
status is observed runtime state, not a replacement for durable status. Per-attempt
usage/latency projection in the UI and full Phase 7 acceptance remain deferred.

This follows the OTel [Python library/API and application/SDK separation](https://opentelemetry.io/docs/languages/python/instrumentation/).
The locked SDK's batch implementation was also inspected for shutdown/timeout
semantics; the documented limits describe this implementation, not guaranteed
collector delivery.
