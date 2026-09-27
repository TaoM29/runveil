# ADR 0009: Typed, authorized tool dispatch

- Status: Accepted for Phase 4A
- Date: 2026-09-26

## Decision

Implement the next roadmap slice inside `runveil_core`: a small immutable tool
binding, registry and explicit policy. Bind native async handlers to strict Pydantic
input/output contracts. Generate advertised input schemas from those same types;
validate arguments before calling and serialized output before returning. Bound
both JSON objects to 64 KiB. No arbitrary JSON Schema interpreter is introduced.
Keep the fixture as the first registered native read-only tool; repository read and
search, with filesystem containment and disclosure controls, are Phase 4B.

Runtime configuration version 2 pins tool names and permissions with empty defaults.
Operator policy is a separate embedding argument, also empty by default. A call
requires both grants, a registered name, READ permission, and PURE or READ_ONLY
classification. Other permission/side-effect combinations are denied even if
granted; approvals and controlled mutations belong to Phase 6. Filter offers by
this policy and enforce it again at dispatch. Model-supplied names or arguments
cannot grant capabilities. Tool bindings and their honest classifications are
trusted application code, not a sandbox for arbitrary Python.

Version 1 configurations are rejected before lifecycle writes; create a new agent
version explicitly to opt into tool policy. Historical checkpoints and records
remain readable. There is no migration or reinterpretation of historical records.
Definitions include a timeout and an explicit `never` retry policy. Deadlines use
cooperative asyncio cancellation: blocking Python or cancellation-swallowing
handlers are unsupported, not forcibly isolated. Cancellation propagates. Safe
fixed errors distinguish unavailable, denied, invalid input/output, timeout and
handler failure. Raw exceptions and invalid results never enter context/storage.

## Integration and limits

Keep existing requested/completed/failed tool events and atomic outcome/checkpoint
writes. Pass the actual tool name into persistence instead of the hard-coded fixture
name. Commit intent before calling handlers; execute outside transactions. Invalid
arguments and execution failures terminate the run through failed tool outcomes.
Unadvertised model-selected names still fail model action validation, as in ADR
0006; direct registry callers get explicit unavailable/denied errors.

No separate dispatch-start event is claimed: requested means intent only. Registry
bindings are fixed for an execution but are not persisted executable code or
versioned deployment artifacts. The pinned policy and advertised input schemas
are retained in configuration/model requests. A future recovery design must pin or
verify tool implementation versions before replay. No retries, worker, filesystem
access, mutation, approval flow or MCP adapter is added in this slice.
