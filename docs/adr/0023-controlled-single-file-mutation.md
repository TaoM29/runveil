# ADR 0023: Single-use controlled file replacement

- Status: Accepted for Phase 6C
- Date: 2026-10-01

## Decision

Add a new `repository-patch-v1` profile and configuration/checkpoint version 11.
It uses the existing proposal pause, but its immutable WRITE grant and distinct
profile identify approval to apply one exact replacement. Phase 6A/B approvals
cannot authorize it. The operator must separately grant WRITE at execution.
The general ToolRegistry remains read-only; a narrow core-owned approved-patch
branch invokes a bound writer, never a model-supplied handler or arbitrary command.

After approval, validate the fresh full workspace identity, persisted proposal and
model/tool provenance. Commit a `repository.apply_patch` tool intent before I/O.
Migration 0010 adds a partial unique index allowing at most one such intent per
run. The intent contains the exact approved proposal; admission and final dispatch
both recheck the pinned profile, approval, policy and counters/deadline. No retry.

For this bounded local operation only, keep the run/job locks from the final live
claim/history/deadline check through synchronous filesystem replacement and outcome
commit. This is an explicit exception to the usual outside-transaction I/O rule:
it serializes cancellation and other claimants with the write. Cancellation that
wins the run lock prevents writing; cancellation after writing cannot undo it.
A lost database connection can release locks independently of a paused process;
this does not provide OS-level revocation of a writer already dispatched.
Filesystem or database stalls can hold locks; this is not a hard real-time sandbox.
Post-I/O expiry produces an uncertain failure, never a successful late result.

The writer handles one ordinary top-level file, mode 0600 or 0644, owned by the
process user, with one hard link and on the root device. It uses descriptor-relative
nofollow operations, exact UTF-8 preimage validation, a nonblocking advisory root
lock, a private exclusive temporary file, fsync, final inode/metadata/root checks,
atomic replacement and directory fsync. Mode and group are preserved (a staging
group mismatch refuses the write); extended metadata such as ACLs/xattrs is not
preserved, so use ordinary controlled fixtures without such metadata. No nested paths, executable files, links,
creation/deletion, shell, network, Git operation or multi-file patch is supported.

The checkout must be operator-controlled and exclusively assigned to this work.
Advisory locking coordinates these writers, not arbitrary programs. POSIX rename
cannot atomically compare a preimage; an uncooperative concurrent editor can race
the final check. Hostile concurrent directory moves/metadata manipulation are not
sandboxed. Do not use this adapter against an adversarial/shared checkout. This is
the same trusted-host boundary as existing repository adapters, with a narrower
write surface; stronger process/container isolation remains later work.

## Uncertain outcomes and recovery

A filesystem change and PostgreSQL outcome cannot commit atomically. Death or a
failed database commit can leave a REQUESTED mutation that may already have changed
the file. Recovery under a new claim records `patch_outcome_unknown`, without any
filesystem access or replay, even if current bytes match before/after text. That
cleanup verifies pinned profile/configuration, approval/provenance and the exact
single outstanding mutation. It deliberately does not require recapturing the old
workspace, which may have changed because of the authorized write. This exemption
can only terminate uncertain work; it cannot dispatch anything. Completed terminal
runs are not selected, so duplicates do not rebind or write.

A crash can leave a private `.runveil-*` staging file. It is never interpreted or
reused; operators may inspect/remove it after confirming no live writer. Errors
after replacement is attempted are uncertain; do not claim that FAILED means the
file was unchanged. There is no automatic rollback, retry, reconciliation or
exactly-once guarantee. Inspection exposes the mutation record/error.

No API/UI, authenticated reviewer identity, hosted provider or broker extension.
The offline provider proposes a fixed marker change. Next, expose the completed
approval workflow through an appropriately authenticated operator API/UI.

The root directory must be owned by the process user and not group/other-writable.
The staged pathname must still refer to the opened private inode before replacement.
