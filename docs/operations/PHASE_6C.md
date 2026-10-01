# Phase 6C handoff — controlled single-file replacement

Verified 2026-10-01. Implemented; stopped for review. No commit or push.

## Scope and decisions

Started from a clean worktree containing Phase 6B. Inspected AGENTS.md, charter,
roadmap, architecture, development/CI checks, approval/claim/checkpoint integration,
repository descriptor/snapshot boundaries and accepted approval/reliability ADRs.
The next coherent slice was one explicitly new write-capable profile, not adoption
of existing review-only approvals.

Implemented `repository-patch-v1` and version 11: the offline provider reads one
file and proposes its fixed marker change; human approval and a separate operator
WRITE grant permit one exact replacement. The general ToolRegistry still denies
mutations. The core's narrow approved-patch branch binds the persisted proposal,
workspace and policy, then commits one `repository.apply_patch` intent before I/O.
Migration 0010's partial unique index prevents another intent in that run.

The final store boundary rechecks claim/history/deadline, approval/provenance and
policy, holding row locks through the synchronous local write and outcome commit.
The adapter validates one top-level regular file, root/file ownership and modes,
links, exact preimage and final inode/metadata identity. It stages privately,
fsyncs and atomically replaces. Root advisory locking coordinates these writers.
The original deadline and invocation accounting remain active.

Filesystem replacement and database commit cannot be atomic. Unresolved mutation
intent terminates as `patch_outcome_unknown` under a fresh claim, without filesystem
access or replay. The old workspace need not be reconstructible for this
terminal-only cleanup. Terminal duplicates do not capture or write anything.
Review-only inspectors now refuse patch runs to avoid misleading no-write output.

[ADR 0023](../adr/0023-controlled-single-file-mutation.md) records the transaction/I/O
exception, constrained trusted-checkout scope and uncertain-effect semantics.
No dependency, package, manifest or lockfile change was needed.

## Files created

- `packages/agent_core/src/runveil_core/mutations.py`: narrow writer contract,
  profile/tool identity, operator/pinned grant check and uncertain-outcome marker.
- `packages/tool_runtime/src/runveil_tools/patch.py`: bounded descriptor-relative writer.
- `packages/persistence/src/runveil_persistence/mutations.py`: exact persisted authorization.
- `packages/persistence/migrations/versions/0010_single_patch_intent.py`: unique intent index.
- `apps/worker/src/runveil_worker/patch_worker.py`: explicit profile, terminal-only
  recovery and submit/work/inspect/approve/reject CLI.
- `packages/tool_runtime/tests/test_patch.py`: filesystem and both-grant boundaries.
- `packages/persistence/tests/test_patch_worker.py`: six integration cases for
  actual application, profile isolation, interruptions, fences and rejection/drift.
- `docs/adr/0023-controlled-single-file-mutation.md`: decision and trade-offs.
- `docs/operations/PATCHES.md`: usage and recovery procedure.
- `docs/operations/PHASE_6C.md`: this handoff.

## Files modified

- `packages/agent_core/src/runveil_core/runtime.py`: version 11 and core-approved
  mutation branch after existing approval suspension.
- `packages/persistence/src/runveil_persistence/execution.py`: intent validation,
  final guarded application/outcome and uncertain-intent termination.
- `packages/persistence/src/runveil_persistence/worker_approvals.py`: explicit
  version/profile mapping and separate decision profile selection.
- `packages/persistence/src/runveil_persistence/models.py`: unique partial index metadata.
- `apps/worker/src/runveil_worker/approvals.py`, `apps/worker/src/runveil_worker/review_worker.py`:
  restrict inspection to their review-only profile.
- `README.md`, `ROADMAP.md`, `ARCHITECTURE.md`: current scope and next review gate.
- `docs/operations/APPROVALS.md`, `docs/operations/DEVELOPMENT.md`,
  `docs/operations/PERSISTENCE.md`, `docs/operations/WORKER.md`: operations/boundary updates.

## Verification

Local Python 3.12.14, uv 0.12.19, Node 24.19.0, PostgreSQL 17.9. No hosted CI, paid
provider or AWS calls. All writes used task-owned temporary fixture files.

```sh
POSTGRES_USER=runveil POSTGRES_DB=runveil POSTGRES_PORT=54329 POSTGRES_PASSWORD=runveil-local-only docker compose -p runveil-phase6-checks up -d --wait --wait-timeout 90
export DATABASE_URL='postgresql+psycopg://runveil:runveil-local-only@127.0.0.1:54329/runveil'
export RUNVEIL_TEST_DATABASE_URL='postgresql+psycopg://runveil:runveil-local-only@127.0.0.1:54329/postgres'
export PATH=/Users/taom/.nvm/versions/node/v24.19.0/bin:$PATH
```

- `uv sync --locked --all-packages`, `npm ci`: passed; locks unchanged. npm reported
  zero vulnerabilities and existing deprecation/optional script notices.
- `uv run alembic upgrade head`, `uv run alembic check`: passed through 0010 with no
  metadata drift. Existing populated migration/downgrade tests passed in the suite.
- `uv run pytest packages/persistence/tests/test_patch_worker.py packages/tool_runtime/tests/test_patch.py -q --tb=short`:
  **7 passed**. Includes actual file replacement, operator grant denial before
  intent, review-profile refusal, rejection, workspace drift, cancellation/lease
  invalidation before dispatch, interrupted intent and interruption immediately
  after replacement. The latter rolls back the outcome but leaves changed bytes;
  recovery terminates without touching them. Raw duplicate intent violates the index.
- `uv run pytest -m 'not integration'`: **134 passed**, 142 deselected.
- `uv run pytest -m integration`: **142 passed**, 134 deselected; no failures/skips.
- After final root/staging checks and configuration validation refinement,
  `uv run pytest packages/persistence/tests/test_patch_worker.py packages/tool_runtime/tests/test_patch.py packages/agent_core/tests/test_runtime_policy.py -q --tb=short`:
  **14 passed**. The full suite was not repeated after these focused refinements.
- `uv run python scripts/phase5_acceptance.py`: passed the existing actual SIGKILL
  checkpoint/uncertain-intent scenarios, active-lease deferral, duplicate delivery
  and disposable database cleanup. New patch interruption tests use deterministic
  cancellation/fault injection, not a new SIGKILL harness.
- `uv run ruff format --check .`, `uv run ruff check .`, `uv run mypy`: passed;
  92 files strictly typed.
- `npm run format:check`, `npm run lint`, `npm run typecheck`, `npm test`,
  `npm run build`: passed; one frontend test.
- `uv run python scripts/smoke.py`: passed with `DATABASE_URL` set and unset,
  covering health, production home page and both readiness outcomes.
- Separate-process exercises through `uv run python -` invoked the CLI on public
  temporary fixtures: submit, pause, inspect, approve/apply and reject, exact file
  contents, terminal duplicate work, duplicate decisions (exit 1, `patch_failed`),
  and refusal by both review-only inspectors. Stable-source runs passed.
- One early CLI exercise overlapped source formatting: its pinned implementation
  digest no longer matched, so continuation safely refused. Inspection confirmed
  the mismatch; the task-owned fixture run was cancelled and evidence retained.
  Repeating after source stabilized passed. No approval or binding was rewritten.
- `git diff --check`: passed.

The session's Compose instance was stopped after verification, retaining its
volume. Integration/acceptance databases cleaned themselves up. The isolated
development database retains terminal CLI fixture evidence; temporary directories
were removed. There are no task-owned live writers.

## Limits and next slice

Use only an exclusively assigned, operator-controlled checkout. This is not a
sandbox against hostile concurrent host processes. POSIX replacement cannot
atomically compare a preimage; other programs must not edit/move the checkout.
Advisory locking does not control them. Database connection loss or an OS pause
cannot forcibly revoke an already-dispatched writer. Blocking filesystem I/O can
hold row locks, and post-I/O expiry is conservatively uncertain.

Only one ordinary top-level file is supported, with restrictive root ownership/
permissions and file modes 0600/0644. No links, executable files, nested paths,
creation/deletion, shell/network or Git actions. Mode/group are preserved;
ACLs/xattrs are not. Use plain fixtures. Crash-left staging files require manual
inspection/cleanup once no writer is live. FAILED or CANCELLED does not prove the
file is unchanged; inspect mutation evidence. No automatic replay, rollback or
exactly-once claim is made. Approval history can contain disclosed source text;
operators must keep secrets out.

Phase 6's authenticated HTTP/API and UI surfaces remain outstanding. Next: a small
operator proposal-inspection and approve/reject API/UI with explicit authentication,
profile separation and the same revision/digest and write-authorization boundaries.
Review this slice before proceeding.
