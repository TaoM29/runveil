# ADR 0024: Local operator approval API

- Status: Accepted
- Date: 2026-10-01

## Context

Phase 6C has durable approval and controlled patch execution, exposed through local
CLIs. The next boundary is authenticated HTTP inspection and decisions. Build and
review that boundary before adding a browser client; Phase 6 UI acceptance remains
open. This is a local single-operator deployment, not a multi-tenant control plane.

## Decision

The API exposes `GET /approvals/{run_id}` and
`POST /approvals/{run_id}/decision`. A configured, randomly generated URL-safe
bearer token authorizes both operations for all supported approvals in this
installation. Missing or invalid configuration disables the surface. Authentication
precedes body parsing and database access. Startup retains a SHA-256 digest;
comparison uses constant-time digest comparison. No credential enters domain
configuration, events or responses. Rotation requires an API restart. Bind to
loopback; network exposure requires a separately reviewed deployment and TLS.

Inspection takes the same run-row lock as the resolvers and returns exact bounded
proposal content, approval identity/digest/status, run revision/status, pinned
workspace fingerprints, profile and mutation outcome. Only standalone Phase 6A
review and the Phase 6B/6C job/schema pairs are supported. There is no discovery,
submission, work dispatch, filesystem access or grant endpoint.

Decisions bind the inspected profile, approval ID, run revision and content digest.
The API owns one transaction and delegates to the existing resolver for that
profile. Success is sent only after commit. Profile and approval-ID checks are
additional HTTP binding checks, not replacements for resolver history/provenance
checks. Approval never grants operator WRITE, extends deadlines, claims a job or
bypasses workspace verification. Review-only approvals remain review-only.

Decision JSON is strict, forbids unknown fields and is limited to 2 KiB while
streaming. Body consumption and database work share a five-second cooperative
request timeout. Errors use fixed codes without reflecting inputs, credentials or
database exceptions. Responses use `Cache-Control: no-store`. No cookies, CORS or
query-string credentials are supported. HTTP retries are not automatic: after a
lost response or timeout, inspect before making another decision. A timeout during
commit can leave an ambiguous client outcome even though database atomicity holds.

## Consequences

The shared credential is a capability for one trusted operator, not individual
reviewer identity, per-run ACLs, tenant isolation or a multi-user audit trail.
Existing decision events record the durable decision without claiming a named
human actor. Generating a high-entropy token is an operational requirement; format
validation alone cannot prove entropy. API servers/proxies must not log bearer
headers or proposal bodies. Application timeouts/body limits are not a complete
public-service denial-of-service defense.

No persistence schema or runtime/writer behavior changes. Direct API dependencies
on core and SQLAlchemy are declared explicitly. A minimal console using this
boundary, safe credential handling and clear profile-specific consequences is the
next slice. Full Phase 6 acceptance is not claimed here.
