# Durable patch review

This is a durable **review-only** workflow. It cannot apply patches. Existing
model/tool workers still deny mutations. `SUCCEEDED` means the proposal review
completed, never that a file was changed. Phase 6's writing tool, hosted model integration,
HTTP endpoints and UI are not implemented yet. The Phase 6B worker integration is
documented below.

After the [development setup](DEVELOPMENT.md), with `DATABASE_URL` exported:

```sh
uv run alembic upgrade head
uv run python -m runveil_worker.approvals demo
uv run python -m runveil_worker.approvals inspect --run-id <run-id>
uv run python -m runveil_worker.approvals approve --run-id <run-id> --expected-revision 2 --expected-digest <digest>
# Or reject instead, using the same inspected revision and digest:
uv run python -m runveil_worker.approvals reject --run-id <run-id> --expected-revision 2 --expected-digest <digest>
```

`demo` persists a fixed replacement of `example.txt` text from `before` to `after`
and leaves the run `WAITING_FOR_APPROVAL`. It does not create/read that file.
Inspection returns the exact proposal, request ID, digest, status and run revision.
Separate invocations reconstruct everything from PostgreSQL. Approve/reject must
use the inspected revision and digest; stale, duplicate, cancelled or competing
decisions fail with the fixed `approval_failed` message and nonzero exit code.
Inspect again to discover the committed result. The CLI prints success only after
commit and JSON-escapes untrusted proposal text.

Approval commits the decision, RUNNING transition, review-result checkpoint and
SUCCEEDED transition in one transaction. Rejection commits the decision and FAILED
transition without resuming execution. Cancellation uses the existing trusted
lifecycle repository; a pending record on a cancelled run is historical data and
cannot be resolved. There is no expiry, notification or polling requirement for
this review-only workflow. Existing worker budgets are not used or extended.

The Python `ApprovalRepository` provides request/get/resolve operations inside
caller-owned transactions. Request accepts only a fresh, unenrolled run whose
immutable configuration is exactly `{"workflow": "patch-review-v1"}`. Proposal
input is one relative path plus bounded before/after text, with a 64 KiB canonical
JSON limit. Paths exclude traversal, empty/dot segments, backslashes and control
characters. This is validation of review data, not filesystem containment or proof
that the supplied before-text matches a workspace. Roll back on any error.

Use only non-sensitive proposal text: it is intentionally retained in PostgreSQL
and returned by inspection. The database credential represents trusted operator
access; there is no authenticated reviewer identity or public endpoint. A future
writer must establish its own single-use execution, workspace and policy checks;
these approved reviews must not be treated as mutation authorization. See
[ADR 0021](../adr/0021-durable-patch-review.md).

## Workspace-bound worker review (Phase 6B)

The separate `repository-review-v1` profile uses the core execution loop and an
offline model provider. It reads one operator-disclosed snapshot file, proposes
appending a fixed marker, validates the exact before-text, and pauses. It still
cannot apply a patch. Files must be non-sensitive UTF-8 and at most 4096 characters;
normal repository containment, allowlist and byte limits also apply.

With `DATABASE_URL` configured, use an existing controlled fixture checkout:

```sh
uv run python -m runveil_worker.review_worker submit --repository-root /absolute/fixture --file example.txt
uv run python -m runveil_worker.review_worker work --run-id <run-id> --repository-root /absolute/fixture --file example.txt
uv run python -m runveil_worker.review_worker inspect --run-id <run-id>
uv run python -m runveil_worker.review_worker approve --run-id <run-id> --expected-revision 2 --expected-digest <digest>
uv run python -m runveil_worker.review_worker work --run-id <run-id> --repository-root /absolute/fixture --file example.txt
# Alternatively, reject instead of approving:
uv run python -m runveil_worker.review_worker reject --run-id <run-id> --expected-revision 2 --expected-digest <digest>
```

Inspect the actual revision/digest instead of assuming the example revision.
Inspection includes the exact proposal and pinned workspace identity. `work` is a
single claim attempt and reports `selected`; inspect the run for its lifecycle
result. While waiting it is not claimable. Approval records a decision checkpoint
and makes the run RUNNING, without dispatching work. A later work call recaptures
the snapshot and requires the identical root, content, allowlist and covered tool
implementation. Drift refuses start/resume before new invocation/history writes;
a rejected start may retain its lease until expiry, as with repository-read-v1.
Restore the original binding or administratively cancel; never rewrite the version.

The tool outcome, approval/checkpoint, pause and lease release are one transaction.
Old owners cannot commit after pause. Repeated/concurrent decisions fail closed.
Rejection terminates without another model call. Approval continuation retains
invocation counts, token/cost totals, original deadline and immutable proposal.
The one-hour elapsed budget includes approval wait. An overdue waiting review
remains inspectable and unclaimable; after approval, the next worker finalizes
expiry before any dispatch. Rejection/cancellation needs no workspace recapture.

This profile uses PostgreSQL polling only; no SQS support or retry grant is added.
The model provider and usage/pricing are offline fixtures, not hosted acceptance.
The proposal tool is READ/READ_ONLY because it only validates snapshot data. Both
operator and pinned policy still gate it; WRITE/EXECUTE/NETWORK capabilities remain
denied. Proposal text appears in model/tool history as well as its approval row.
Decisions use trusted local database access, without authenticated reviewer identity.
The Phase 6A CLI/resolver does not resolve these worker approvals. Neither kind of
approved review is permission for a future writer. See
[ADR 0022](../adr/0022-worker-patch-review.md).
