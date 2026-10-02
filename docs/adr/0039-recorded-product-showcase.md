# ADR 0039: Recorded product showcase beside local operator tools

- Status: Accepted for the pre-Phase 11 UI slice
- Date: 2026-10-02

## Decision

Use the committed public Phase 10G six-run artifact and Phase 10F failed-validation
artifact to demonstrate the completed workflow without widening live API authority.
The frontend imports these two files explicitly and projects selected fields into
an overview, filterable recorded-runs list and per-run evidence view. Every screen
identifies the records as read-only, scripted fixture evidence. The failed-validation
run is explicitly labelled fault injection. Counts derive from these records; no
live activity, token usage, cost or model-quality metrics are invented.

The overview lives at `/`, the archive at `/runs`, and exact retained records at
`/runs/[runId]`. Unknown IDs return not found. The earlier approval console moves
to `/approvals`; `/traces` remains the authenticated, read-only live inspection
surface. This supersedes ADR 0025's home-page placement and the earlier UI-only
scope limits in ADRs 0025/0027. Their security and lifecycle decisions still apply.

No backend, runtime, storage, proxy, token or authorization contract changes.
The recorded archive has no mutation controls or API requests. It does not turn
private live traces into public data, discover database runs, start workers or
approve sandbox patches. Phase 10 approval remains in the trusted local CLI.
The existing browser decision API still supports only its original profiles.

Navigation away from either operator surface remains full-document navigation,
so credentials and in-flight state are discarded. Exact proposal/output content
renders as React text, including an escaped proposal disclosure. Existing acknowledgement,
inspection binding, stale response, uncertain decision, pagination, no-store and
separate-token behavior remain unchanged. The source artifacts themselves are not
modified or recopied into a second maintained fixture set.

## Presentation

Use a light operations-console layout with a restrained indigo action accent,
explicit semantic status labels, native form/disclosure controls, system sans text,
and monospace for code and identifiers. The overview explains one actual repair;
the detail view separates tool completion, decision, mutation and test outcome.
Search hits, exact diff, before/after, test logs, identity digests and source paths
remain available. A successful tool call is never relabelled as a passing test.

This is portfolio presentation of existing public evidence, not authorization to
expose the local operator deployment publicly. Public hosting, live discovery,
Phase 10 browser decisions and MCP integration require separate slices.
