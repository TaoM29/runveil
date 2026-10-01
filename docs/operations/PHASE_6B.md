# Phase 6B handoff — workspace-bound worker approval

Verified 2026-10-01. Implemented; stopped for review. No commit or push.

## Implementation and decisions

Started with a clean worktree containing Phase 6A. Inspected the charter, current
roadmap, architecture, development/CI checks, approval implementation, worker
claims/recovery, repository snapshot bindings and relevant accepted ADRs. The
Phase 6A resolver intentionally excludes enrolled runs; extending it blindly would
bypass worker checkpoint and ownership assumptions.

Added the separate offline `repository-review-v1` profile on the existing core
execution loop. It reads one disclosed snapshot file, makes a model ToolAction
proposal, validates exact path/preimage through a read-only tool, and pauses for
one human decision. Configuration/checkpoint version 10 retains approval identity
and resolution state. Proposal completion, approval row/event/checkpoint, waiting
transition and lease release are one fenced transaction. Approval resolution
checkpoints a RUNNING continuation; a new worker must reconstruct the identical
workspace and validate approval/model/tool provenance before continuing. Rejection
terminates without another invocation.

[ADR 0022](../adr/0022-worker-patch-review.md) records the boundary: validation is
read-only; no patch writer or reusable mutation authority exists. Both pinned and
operator grants remain required. Existing read-only binding hashes are unchanged;
the new review adapter adds its own source/contract fingerprint to workspace
identity. Phase 6A remains separate and unchanged. No migration, package, dependency,
manifest or lockfile change was needed.

Counts and the original one-hour deadline survive approval wait. Waiting jobs are
not selected. Approval of an expired review permits normal worker cleanup, which
fails before another dispatch. Uncertain proposal intent is never replayed.

## Files created

- `apps/worker/src/runveil_worker/review_worker.py`: fixed offline provider/profile,
  submission, per-run worker and inspection/decision CLI.
- `packages/tool_runtime/src/runveil_tools/review.py`: snapshot/preimage validation
  binding and additional implementation identity.
- `packages/persistence/src/runveil_persistence/worker_approvals.py`: atomic pause,
  provenance verification and trusted local decision boundary.
- `packages/tool_runtime/tests/test_review.py`: both policy grants, snapshot-only
  access, wrong path/preimage and unchanged-file checks.
- `packages/persistence/tests/test_worker_approvals.py`: six integration cases across
  restart/drift, decision boundaries, three injected interruption points and expiry.
- `docs/adr/0022-worker-patch-review.md`: architectural decision and limits.
- `docs/operations/PHASE_6B.md`: this handoff.

## Files modified

- `packages/agent_core/src/runveil_core/approvals.py`: proposal tool/profile identities.
- `packages/agent_core/src/runveil_core/runtime.py`: version 10, approval checkpoint
  fields and return immediately after committed proposal review suspension.
- `packages/persistence/src/runveil_persistence/execution.py`: integrate atomic pause
  and approval provenance validation on recovery.
- `README.md`, `ROADMAP.md`, `ARCHITECTURE.md`: current status, integration and next gate.
- `docs/operations/APPROVALS.md`, `docs/operations/WORKER.md`,
  `docs/operations/PERSISTENCE.md`: operator commands and persistence/recovery behavior.

## Verification

Local Python 3.12.14, uv 0.12.19, Node 24.19.0 and PostgreSQL 17.9. No hosted CI run,
live provider/AWS calls, paid tests or patch writes. Used the isolated Compose
project retained from Phase 6A, with explicit local-only credentials:

```sh
POSTGRES_USER=runveil POSTGRES_DB=runveil POSTGRES_PORT=54329 POSTGRES_PASSWORD=runveil-local-only docker compose -p runveil-phase6-checks up -d --wait --wait-timeout 90
export DATABASE_URL='postgresql+psycopg://runveil:runveil-local-only@127.0.0.1:54329/runveil'
export RUNVEIL_TEST_DATABASE_URL='postgresql+psycopg://runveil:runveil-local-only@127.0.0.1:54329/postgres'
export PATH=/Users/taom/.nvm/versions/node/v24.19.0/bin:$PATH
```

- `uv sync --locked --all-packages`, `npm ci`: passed; locks unchanged. npm reported
  zero vulnerabilities and existing ESLint deprecation/optional script notices.
- `uv run alembic upgrade head`, `uv run alembic check`: passed, existing 0009 head,
  no metadata drift.
- `uv run pytest packages/persistence/tests/test_worker_approvals.py packages/tool_runtime/tests/test_review.py -q --tb=short`:
  **7 passed**, including after final provenance/fingerprint changes.
- `uv run pytest -m 'not integration'`: **133 passed**, 136 deselected.
- `uv run pytest -m integration`: **136 passed**, 133 deselected, no failures/skips.
- `uv run python scripts/phase5_acceptance.py`: passed actual SIGKILL checkpoint
  recovery/success, uncertain-intent failure, active-lease deferral, duplicate
  acknowledgement and owned database cleanup. New Phase 6B interruption tests use
  deterministic cancellation/fault injection; they do not claim new SIGKILL tests.
- `uv run ruff format --check .`, `uv run ruff check .`, `uv run mypy`: passed;
  85 files strictly typed.
- `npm run format:check`, `npm run lint`, `npm run typecheck`, `npm test`,
  `npm run build`: passed; one frontend test.
- `uv run python scripts/smoke.py`: passed with `DATABASE_URL` set and unset;
  API/web health, production home page and both readiness cases.
- Separate subprocess exercise through `uv run python -` ran the documented
  `python -m runveil_worker.review_worker` submit/work/inspect/approve/reject commands
  on a temporary public fixture. Verified pause across processes, no selection
  while pending, approved RUNNING then fresh-process SUCCEEDED, rejection FAILED,
  duplicate decisions returning exit 1 with `review_failed`, and unchanged file text.
- `git diff --check`: passed.

Integration evidence includes preserved deadline/counters, exact approval identity,
content and review-implementation drift refusal before history/dispatch, rollback
of decisions, competing rejections, cancellation, stale worker fencing, atomic
pause rollback and conservative recovery after unresolved proposal intent. Tests
verify only one approval and two tool calls across successful continuation.

The session's Compose instance was stopped after verification with volumes
retained. Test/acceptance databases clean themselves up; the isolated development
database retains two terminal CLI examples. The temporary fixture was removed.

## Remaining scope and next slice

Phase 6 remains incomplete: no controlled writer, authenticated reviewer identity,
HTTP/UI, broker support for this profile or live hosted approval acceptance.
Proposals and disclosed text persist in model/tool and approval history; operators
must exclude secrets. Snapshot capture is not an atomic filesystem lock. Waiting
reviews have no automatic expiry sweeper; rejection/cancellation remains available,
and approved overdue work expires before dispatch. Binding rejection can retain a
lease until expiry, matching existing repository recovery behavior.

Next: one controlled single-file writer in an explicitly new profile, with a
single-use durable mutation intent, exact approval/workspace/policy binding, fresh
preimage validation and conservative uncertain-effect handling. Existing review-only
approvals must never become mutation permissions. Review this slice before proceeding.
