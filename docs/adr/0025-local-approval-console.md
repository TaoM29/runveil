# ADR 0025: Small local approval console

- Status: Accepted for Phase 6E
- Date: 2026-10-01

## Decision

Replace the foundation landing page with one operational screen: enter an existing
run ID and the local operator token, inspect its exact proposal, approve or reject,
and refresh to inspect subsequent worker progress. No listing, run submission,
worker start, policy editing, trace dashboard or product navigation is added.

The token is entered by the operator and held in React memory only. It is never
in a URL, cookie, local/session storage, server-rendered content or a server-side
shared credential. Forget and pagehide clear it and proposal data. Browser password
managers/extensions are outside this guarantee; autocomplete is discouraged, not
controlled by the application. An active malicious same-origin script or browser
extension can still access an entered token. Shared-token limitations remain those
of ADR 0024.

A Next route forwards only GET inspection or POST decision to the fixed local API
origin explicitly configured by `RUNVEIL_API_ORIGIN=http://127.0.0.1:<port>`.
Missing/invalid configuration fails closed. No client-selected endpoint, arbitrary
path, redirect, ambient cookie, CORS or server-supplied token is allowed. The caller's
bearer is forwarded; the API remains the authentication/authorization authority.
Requests require a UUID and correctly shaped bearer header. Host must be loopback;
POST requires matching HTTP Origin, and cross-site requests are refused. Compare
Origin with the local Host header, not Next's normalized internal URL or forwarded
host headers. Remote reverse proxies/TLS deployment are outside this local slice.

The proxy streams at most 2 KiB of decision input and 128 KiB of JSON response under
an eight-second cooperative deadline. Only selected failure statuses are relayed,
with fixed non-reflecting errors. No upstream cookies or locations are forwarded.
Responses are no-store. Console headers deny framing and suppress referrers.

The UI validates inspection shape and requested run identity before offering a
decision. It renders proposal content as text, includes a complete escaped JSON
view for whitespace inspection, and displays the three distinct profile
consequences. It requires an explicit inspection acknowledgement before either
choice. That acknowledgement is usability, not an authorization boundary.
The API remains responsible for exact profile/approval-ID/revision/digest binding,
provenance and transactional one-time decisions. The worker still independently
requires its write grant and full workspace/preimage checks.

Every request invalidates the previous inspection and acknowledgement. Input
changes/forget/pagehide invalidate outstanding responses. Failures after a decision
and interruptions during decisions report an uncertain outcome and require fresh
inspection, without automatic retry. Approved status is never presented as proof
that a file was written; mutation evidence and uncertain/failed-write warnings
are shown separately. Fingerprints are pinned identity, not current-file checks.

## Consequences and evidence

Core, API, persistence and worker code are unchanged. One development dependency,
jsdom, enables focused real React DOM lifecycle/decision tests; no runtime UI
library or general client framework is added. Proxy tests exercise authority and
resource boundaries. Real production web/API/PostgreSQL checks cover approval and
rejection followed by separately authorized worker execution. Browser verification
checks initial layout; automated component tests are not a full-browser end-to-end
suite. Final Phase 6 closure review should consolidate acceptance evidence before
Phase 7 begins.
