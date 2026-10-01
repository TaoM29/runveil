# Execution telemetry

Phase 7C adds opt-in OpenTelemetry spans and structured JSON span logs to the
existing worker commands. [Durable traces and the trace console](TRACES.md) remain
the source of persisted execution evidence. Telemetry requires no API credential
and grants no inspection, approval, worker-selection or WRITE authority.

## Enable local output

Install the locked workspace dependencies and configure the database as described
in [development](DEVELOPMENT.md). For an existing offline fixture run:

```sh
RUNVEIL_TELEMETRY=json uv run python -m runveil_worker work \
  --once --run-id <run-uuid> --profile fixture-calls-v1
```

The same environment switch applies to the existing review-worker, patch-worker
and SQS CLI entry points. Their existing grants, bindings and configuration are
still required. Unset the variable to disable instrumentation; only the exact value
`json` enables it. Submission alone emits no execution span. Existing stdout status
lines remain unchanged; completed spans are one JSON record per stderr line.
Library callers must explicitly scope a trusted tracer with
`runveil_core.telemetry.using_tracer`; calling a worker function does not read the
telemetry environment or configure an SDK.

No collector, network exporter, global tracer, automatic instrumentation, ambient
trace/baggage propagation or environment-derived resource labels are configured.
The core depends on the OTel API; the worker owns the SDK and output configuration.

## Correlation and meaning

Each `agent.execute` call creates a root, including each retry or approval resume.
`run_id` correlates those separate trace IDs with the durable run. Child
`model.attempt`, `tool.dispatch` and `tool.apply_patch` spans include the durable
invocation ID and committed request event sequence. Intents that are never
replayed do not acquire a fabricated dispatch span. Claim/admission, operator
decisions and uncertain-patch cleanup outside core execution are not instrumented.

Records contain a fixed event/service/name, trace/span/parent IDs, start/end epoch
nanoseconds and allowlisted attributes. Root outcomes distinguish success, failure,
approval wait, retry wait and exceptions/interruption. Returned roots report
cumulative checkpoint steps, retries and available token/cost accounting. Unknown
usage/cost counts remain explicit; older schemas omit unavailable accounting.
Model spans include observed usage when available and a completeness flag.
Never sum cumulative root totals across resumes. Cost is estimated nano-USD, not
provider billing.

A child's `returned` outcome means its observed call returned, not that its result
was committed: budget checks or persistence can still fail. Root completion also
precedes worker-level finalization. Timings are local observed elapsed wall time:
model timing includes response validation; failed tool timing can include failure
persistence; patch timing encloses the existing fenced store operation. They are
not pure provider latency, nor the durable request-to-completion interval displayed
by the UI. Spans can be absent, incomplete, duplicated across separate observations,
or disagree with the last committed state after a crash. Reconcile via durable IDs.

## Privacy, failures and lifecycle

The runtime supplies no prompts, model output, arguments/results, file paths,
provider/model labels, arbitrary tool names, credentials or raw exception text.
The exporter independently selects fixed names/outcomes, canonical UUIDs, bounded
nonnegative integers and booleans. It never serializes SDK events, status text or
resource attributes. Records are capped at 4096 UTF-8 bytes before the newline.
Run IDs, usage and timing are operational metadata; protect access to any captured
stderr output. This switch does not make unrelated application stderr structured.

The SDK batch processor has a 256-span queue, batches of at most 32 and a one-second
schedule. Output I/O runs in its background thread. Saturation, broken output and
process death can lose records; output errors are swallowed without exposing their
contents. Guarded span start/update/end errors do not change returned runtime state,
trigger retries, or replace original exceptions/cancellation. No telemetry operation
runs inside the patch store's transaction/filesystem critical section.

After execution and database cleanup, the CLI requests SDK shutdown to drain output.
A stalled stderr sink can delay exit by the SDK's default join of up to 30 seconds;
the SDK export-timeout setting does not forcibly interrupt a blocked Python write.
There is no guaranteed delivery or hard time isolation from a custom synchronous
tracer supplied by a library caller. Abrupt shutdown may omit active spans entirely.
No exporter failure authorizes replay or repairs persisted history.

See [ADR 0028](../adr/0028-execution-telemetry.md) and
[Phase 7C verification](PHASE_7C.md). [Phase 7 closure](PHASE_7.md) demonstrates
integrated local acceptance. Collector integration, metrics, cross-process
propagation and per-attempt UI usage projection remain separate work.
