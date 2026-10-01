# ADR 0022: Workspace-bound worker approval suspension

- Status: Accepted for Phase 6B
- Date: 2026-10-01

## Decision

Add the offline `repository-review-v1` worker profile and configuration/checkpoint
version 10. It reads one explicitly disclosed snapshot file (at most 4096
characters), then produces a single-file replacement through the existing model
ToolAction contract. `repository.propose_patch` is a READ/READ_ONLY validation tool:
it checks the exact path and before-text against the captured snapshot and returns
the proposal. It has no write capability. Both pinned and operator grants still
control offering and dispatch. Existing profiles and mutation denial are unchanged.

The successful validation outcome, checkpoint containing a new approval ID,
approval row/event, WAITING_FOR_APPROVAL transition and lease release commit in
one fenced transaction. Core returns without another invocation. A crash before
that commit leaves ordinary uncertain tool intent, which fails without replay;
a crash afterwards leaves one durable, unclaimable pending review.

A separate trusted operator resolver checks run revision, digest, profile, pinned
configuration, checkpoint and completed tool/model provenance. Approval records
its event, transitions to RUNNING and checkpoints the decision without acquiring
an execution lease or dispatching anything. Rejection records its decision and
FAILED transition. Concurrent/duplicate/cancelled decisions fail closed. The original
Phase 6A resolver still refuses enrolled runs; its approvals are not adopted.

A new worker claim captures the repository again and must match the entire pinned
configuration before continuation. Recovery validates the approval row and its
completed invocation against checkpoint state. Root, allowlist, content and covered
implementation drift refuse execution. The review adapter's source fingerprint
extends the existing repository fingerprint without changing older bindings.
The digest binds proposal text; its immutable run binds workspace identity.
Inspection exposes both. Approval never permits a changed workspace.

Approval wait consumes the existing elapsed budget; no deadline or counters are
reset. Pending reviews are not polled even when overdue. Approval makes the run
eligible; normal worker expiry then fails it before another dispatch. Operators
may reject/cancel without restoring workspace contents. No sweeper is introduced.

## Limits and next boundary

The provider is deterministic and offline; this verifies runtime model-action
integration, not live hosted acceptance. One proposal is allowed per run. Success
means approved review completed, not patch applied. Before/after text is retained
in existing model/tool evidence and the approval row, so disclosed files must not
contain secrets. Snapshot validation is not a filesystem lock or atomic capture.

No schema migration, broker extension, HTTP/UI, reviewer authentication or mutation
is added. A future writer needs an explicitly new execution contract: approval
bound to exact proposal/workspace/policy, one durable mutation intent, fresh
preimage check and fail-closed uncertain-effect recovery. Do not turn these
review-only approvals into write permission or replay them as side effects.
