# Local run trace API

Phase 7A exposes `GET /runs/{run_id}/trace`. It reads committed PostgreSQL evidence;
it never starts work, resolves approval, grants WRITE or accesses the filesystem.
There is no run listing. Obtain the run ID from the existing submission commands.

## Setup

Use the [development setup](DEVELOPMENT.md), migrate the database, and bind the API
to loopback. Set `RUNVEIL_TRACE_TOKEN` to a separately generated URL-safe secret
(`secrets.token_urlsafe(32)`), then start/restart the API. Missing or invalid
configuration disables traces. The token is accepted only in an
`Authorization: Bearer …` header, never cookies or query parameters. Keep it out
of shell history, logs, screenshots and saved requests. Rotation requires restart.
Do not reuse the approval credential: a trace credential must not authorize decisions.
The existing `RUNVEIL_APPROVAL_TOKEN` and approval endpoints are unchanged.

This is a shared local operator capability for all run IDs, not per-run access
control or named identity. Remote/public access requires a separate security review.
Phase 7B adds the local browser console described below. OpenAPI describes the response schema;
pagination parameters are documented here because authentication runs before parsing.

## Pagination and consistency

Start with `?limit=50` (default; allowed 1–100). The response includes
`event_sequence`, the committed snapshot watermark, and `next_after_sequence`.
If the latter is non-null, request the next page with
`?after_sequence=<next_after_sequence>&expected_sequence=<event_sequence>&limit=50`.
Continuation without a watermark is rejected. Each page repeats the run summary.
Stop when `next_after_sequence` is null. A 409 `trace_changed` means history advanced;
discard accumulated pages and start again. Do not merge different watermarks.
Active runs may repeatedly invalidate pagination; terminal runs are stable.

A read-only repeatable-read transaction keeps all data within a request consistent
without taking run locks. The event watermark, rather than lifecycle revision,
detects new checkpoints even when the run remains RUNNING. Event sequence orders
the trace; timestamps are descriptive. `history_complete: false` identifies a
migration baseline or missing initial creation evidence, not a reconstructed past.

## Meaning of fields

- Run/version IDs, status, revision and timestamps correlate the evidence.
  Elapsed milliseconds include retries, approval waits and process downtime, from
  first start to finish (or observation time for nonterminal runs).
- Model/tool counts count committed intents, including unresolved requests.
  Request and outcome events carry the same invocation metadata, including its
  current status, safe error code, model/provider or tool name, model provenance,
  and request/completion event sequences. These are snapshot annotations: a request
  event can show its later completed outcome, not its status at the event instant.
- Invocation duration is request-to-persisted-outcome wall time, not provider
  latency. Unresolved requests have null completion/duration, never fabricated zero.
- `retry_of` on a model request identifies its failed predecessor. Checkpoint
  `retries_scheduled` counts schedules, which need not have dispatched yet.
- Checkpoint `tokens` (runtime schema 5+) preserves known input/output components,
  completed attempts and unknown-attempt counts. `cost` (schema 6+) preserves the
  known nano-USD estimate and unknown count. Divide nano-USD by 1,000,000,000 for
  USD. These are pinned-price estimates, not invoices or spending caps. Pending
  intents are not included in completed-attempt accounting. Older/unrecognized
  checkpoint accounting is null, not zero. Failed attempts retain their accounting.
- The checkpoint event sequence identifies the accounting boundary and can precede
  the current run watermark. Error code/final summary are checkpoint evidence,
  not a replacement for current lifecycle state. Final summaries are truncated to
  4096 characters with an explicit flag; artifact paths are omitted.
- Approval ID/status/timestamps describe durable review state. Pending approval
  does not imply that a cancelled run can be approved. Use the existing approval
  inspection/decision surface for authoritative action and exact proposal review.

Raw event payloads, conversations, model content, tool arguments/results, proposals,
workspace paths, credentials and provider response bodies are not returned.
Selected labels and final summary are still operator data, not automatically
redacted text. The console renders them as untrusted text, never HTML.
Per-attempt tokens/provider latency and pricing details are not projected yet.

## Errors and bounds

Responses use `Cache-Control: no-store` and `X-Content-Type-Options: nosniff`.
Authentication precedes UUID/query parsing and database access. Invalid/duplicate
or unknown parameters return 422 without echoing their values. A malformed cursor
beyond existing history returns 409 `trace_unavailable`. Unknown runs return 404
after authentication; disabled configuration returns 503 `traces_disabled`.
Unavailable storage or the five-second cooperative timeout returns 503
`unavailable`; malformed unsupported projection data returns 409 `trace_unavailable`.
Responses above 512 KiB are refused as 503 `trace_too_large`; request a smaller page.
No automatic retries or mutations occur. These are application bounds, not a public
service denial-of-service defense.

Opt-in [OpenTelemetry and structured JSON output](TELEMETRY.md) now correlate
with these durable records. See [ADR 0026](../adr/0026-durable-run-trace.md),
[initial handoff](PHASE_7A.md) and [integrated Phase 7 acceptance](PHASE_7.md).

## Browser console (Phase 7B)

Set `RUNVEIL_API_ORIGIN=http://127.0.0.1:8000` in the web server environment,
using the actual loopback API port, then start the production build or development
server as described in [development](DEVELOPMENT.md). Configure the API's
`RUNVEIL_TRACE_TOKEN` separately; do not set a trace token on the web server.
Open `/traces`, or choose **Live trace** in the console navigation. The recorded
showcase at `/runs` is separate from this authenticated live view.

1. Enter an existing run ID and its installation's read-only trace token.
2. Select **Inspect / refresh**. Read the snapshot status, counts, known usage,
   estimated cost, approval metadata, final summary and ordered execution events.
3. Open **Call correlation** for invocation IDs, source model provenance and
   request/outcome event positions. Request events show the call's current
   snapshot outcome, rather than pretending it already succeeded at request time.
4. Select **Next events** for the next 50 events. Only one page is retained and
   displayed. Refresh returns to the first page. A conflict or malformed response
   clears the view; manually refresh to restart. There is no automatic polling.
5. Use **Forget token and trace** when finished. It clears the credential, run ID
   and evidence; reload and navigation away also clear them. Navigating to `/approvals`
   requires its separate token and a fresh inspection.

Known zero remains zero; missing accounting is **Not recorded**. Unknown usage and
cost retain explicit counts, and cost with unknown attempts is labelled a known
subtotal. Costs display nine decimal places of USD to retain the API's integer
nano-USD precision. Unsafe JavaScript integers are refused rather than rounded.
The original API's incomplete-history, unavailable historical accounting and
summary-truncation limitations remain visible. Unresolved calls have no recorded
duration; approved status does not imply a mutation succeeded. There are no
approval, cancellation, submission or execution controls on this page.

The browser holds credentials/results only in memory: no URLs, cookies, local or
session storage. Extensions, password managers and malicious same-origin scripts
remain outside that guarantee. Use only a trusted local machine. The same-origin
`GET /api/traces/{runId}` proxy forwards only validated pagination and the caller's
bearer to the fixed API origin, with no redirects, cookies or upstream headers.
Next's automatic HEAD is read-only; mutation methods return 405. JSON is bounded
to 512 KiB under an eight-second proxy timeout; the browser aborts after ten seconds.
Errors expose only fixed messages. Existing framing/referrer protections apply.

See [ADR 0027](../adr/0027-local-trace-console.md) and
[Phase 7B verification/handoff](PHASE_7B.md). This completes the focused local UI
slice. [Phase 7 closure evidence](PHASE_7.md) covers integrated local acceptance;
public-demo deployment is not claimed.
