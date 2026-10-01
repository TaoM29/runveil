# Controlled single-file patch worker (Phase 6C)

`repository-patch-v1` is an offline demonstration that can replace **one ordinary
top-level file** after human approval and a separate execution-time WRITE grant.
Use a disposable, exclusively assigned, operator-controlled checkout containing
non-sensitive text. This is not a container sandbox or a general patch command.
The Phase 6A/B review-only workflows cannot authorize writes.

Requirements: the existing [development setup](DEVELOPMENT.md), migration 0010,
one UTF-8 file of at most 4096 characters for the fixture provider, no symlinks or
hard links, file ownership matching the process user, and mode 0600 or 0644.
Nested/hidden paths, executable files, file creation/deletion and multi-file patches
are unsupported. Use plain files without extended metadata: mode/group are
preserved, but ACLs/xattrs are not copied. A staging-group mismatch refuses writing.

## Run and inspect

With `DATABASE_URL` exported and a controlled fixture already present:

```sh
uv run alembic upgrade head
uv run python -m runveil_worker.patch_worker submit --repository-root /absolute/fixture --file example.txt
uv run python -m runveil_worker.patch_worker work --run-id <run-id> --repository-root /absolute/fixture --file example.txt
uv run python -m runveil_worker.patch_worker inspect --run-id <run-id>
uv run python -m runveil_worker.patch_worker approve --run-id <run-id> --expected-revision 2 --expected-digest <digest>
uv run python -m runveil_worker.patch_worker work --run-id <run-id> --repository-root /absolute/fixture --file example.txt --allow-write
uv run python -m runveil_worker.patch_worker inspect --run-id <run-id>
```

Use the revision/digest returned by inspection, not an assumed value. Inspect the
exact before/after proposal and pinned workspace identity. The fixed provider
proposes appending `Reviewed by Runveil.`; there is no live model or paid call.
Submission pins READ and WRITE permissions, but execution still requires
`--allow-write`. The first work invocation only reads/proposes and pauses; approval
alone never writes. Without the final WRITE grant, approved continuation refuses
before creating mutation intent. Such a refusal can retain its lease until expiry.

To reject instead of approving:

```sh
uv run python -m runveil_worker.patch_worker reject --run-id <run-id> --expected-revision 2 --expected-digest <digest>
```

Rejection/cancellation prevents a subsequent write. Decisions use trusted local
database credentials, with revision/digest checks and no authenticated reviewer UI.
The review-only CLIs refuse this profile, including inspection, so they cannot
incorrectly report that no patch was applied. Use the patch CLI's inspection.
`mutation` is null before intent; otherwise it reports the durable status/error.
`work` reports selection/error, not a speculative filesystem outcome.

## Mutation and recovery guarantees

The fresh snapshot must match root, content, allowlist and covered implementation
before intent. The final writer checks exact preimage and metadata again. One
committed `repository.apply_patch` intent precedes I/O, enforced by a per-run unique
index. The intent is consumed even if dispatch never happened. The writer uses an
advisory root lock, descriptor-relative nofollow opens, a private staged file,
fsync and atomic replacement. Its final ownership/history/deadline check and
outcome run under database row locks to serialize normal cancellation/claim races.
The original elapsed deadline and invocation accounting are retained.

The root lock is advisory. Other programs must not modify or move the checkout
while work runs: there is no atomic POSIX preimage-compare-and-replace operation.
The synchronous bounded writer can block on filesystem I/O and cannot be forcibly
revoked across an OS pause/lost database connection. See [ADR 0023](../adr/0023-controlled-single-file-mutation.md)
for this trusted-host limitation and the transaction/I/O trade-off.

If the process dies or outcome commit fails, **the file may already have changed**.
After lease expiry, the same work command terminates an outstanding mutation as
`patch_outcome_unknown`, without recapturing the workspace, requiring WRITE, or
accessing the filesystem. It never replays the mutation, even if the file matches
the old or new text. Expiry during/after replacement is also conservatively unknown.
Inspect the file and database evidence manually. Do not reset a run or manufacture
another approval to retry an uncertain change; establish a new controlled task
from the actual current state. There is no automatic rollback/reconciliation.

A REQUESTED mutation on a CANCELLED run remains historical uncertain evidence;
cancelled runs are not automatically recovered. `FAILED` alone never proves the
file was untouched. A successful committed mutation is terminal, so duplicate
work cannot write again or fail because the original snapshot has changed.

A hard crash may leave a private `.runveil-*` staging file. It is never reopened or
reused automatically. After confirming no live writer, inspect/remove that artifact
manually. Normal errors clean up the staging file. Test fixtures use no secrets;
do not disclose sensitive text into model/tool/approval history.

Migration 0010 adds only the unique intent index. If unsupported historical rows
already contain multiple `repository.apply_patch` calls in one run, migration
fails rather than deleting history. Inspect and resolve schema adoption separately.
Downgrade removes the database's single-intent guard and is not a recovery action.
The [local approval HTTP API](APPROVAL_API.md) can inspect and decide these
approvals through the [local console](APPROVAL_CONSOLE.md); worker execution still
uses the explicit CLI. No SQS support, hosted acceptance, Git commit/push or
arbitrary command execution is included.

The root directory must be owned by the process user and not group/other-writable.
The staged pathname must still refer to the opened private inode before replacement.
