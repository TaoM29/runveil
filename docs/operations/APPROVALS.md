# Local patch review (Phase 6A)

This is a durable **review-only** workflow. It cannot apply patches. Existing
model/tool workers still deny mutations. `SUCCEEDED` means the proposal review
completed, never that a file was changed. Phase 6's writing tool, model integration,
HTTP endpoints and UI are not implemented yet.

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
