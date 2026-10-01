# ADR 0027: Local read-only trace console

- Status: Accepted for Phase 7B
- Date: 2026-10-01

## Decision

Add `/traces` as one operational screen over ADR 0026's existing durable API.
Enter an existing run ID and the separate trace token, inspect/refresh, and move
forward through events. Display one bounded page of 50 events at a time; do not
accumulate an unbounded client history. Refresh starts from the first event.
Every continuation binds the observed watermark. Changed or invalid history
clears the view and requires manual inspection again, without automatic polling.

The page validates response identity, schema, field shapes, safe integer
accounting, event order, invocation correlations, continuation progress and
watermark before rendering. Unknown/legacy accounting remains unavailable;
unknown consumption retains known subtotals and an explicit warning. Integer
nano-USD is formatted exactly to nine decimal places without floating-point
rounding. Durations retain the API's persisted wall-time meaning. Approval is
read-only metadata, not proof of mutation or permission to act. All data is text,
never HTML or executable links; final-summary truncation is visible.

The fixed `/api/traces/{runId}` Next route forwards GET only to the configured
loopback API's `/runs/{runId}/trace`. Next's implicit HEAD is also read-only;
POST and other mutation methods are unsupported. Validate local Host/Origin,
fetch-site, caller bearer shape, UUID and allowed bounded pagination parameters.
Forward only caller authorization; never ambient cookies, arbitrary paths,
client-selected origins, redirects, upstream headers or server-owned credentials.
Responses are no-store, JSON-only and limited to 512 KiB within an eight-second
cooperative timeout. Errors are fixed and non-reflecting. The API still authenticates
using `RUNVEIL_TRACE_TOKEN`, independently of approval credentials.

Credentials, run ID and trace remain in React memory, cleared on Forget/pagehide.
Input edits, refresh, pagination and failures remove the old view; generation
checks discard late responses, including after abort/unmount. Full-document links
between approval and trace pages discard their separate memory state. No token or
run ID is placed in navigation URLs or persistent browser storage. Existing
browser extension/password-manager/same-origin-script limitations remain explicit.

## Consequences

No backend, runtime, worker, database, policy or dependency change is required.
Extract only the existing bounded stream reader for reuse by the two concrete
proxies; approval behavior remains unchanged and its tests continue to run.
There is no generic API/client framework, run discovery, dashboard, submission,
execution control, filtering, export or auto-refresh. This is not a public console.
Telemetry instrumentation and structured logging remain the next separate Phase 7
boundary; the durable trace remains authoritative.
