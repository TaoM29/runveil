# Phase 6A handoff — durable patch review foundation

Verified 2026-10-01. Implemented; stopped for review. No commit or push.

## Scope and decisions

Started from a clean repository. Inspected the charter, roadmap, architecture,
Phase 5 closure/handoff, lifecycle/history/worker boundaries and relevant ADRs.
Phase 5's accepted evidence supports continuing. The next focused slice is a
review-only approval boundary, with mutation still disabled as the roadmap proposed.

Added a bounded single-file before/after proposal, canonical digest, durable
ApprovalRequest, atomic pause and one-time resolution, and a local CLI. Approval
resumes to checkpoint a completed review and succeeds; rejection records its
decision and fails without resuming. Run locks serialize competing decisions;
revision/digest checks reject stale input, duplicates and cancellation. Request
identity and completed outcomes cannot be edited or deleted. Checkpoints/events
retain correlation without duplicating proposal text.

[ADR 0021](../adr/0021-durable-patch-review.md) explains the deliberate isolated
`patch-review-v1` workflow. Existing worker recovery accepts specific checkpoint
tails/configurations and cannot safely adopt approval history without another
integration slice. This implementation refuses enrolled/other-profile runs and
adds no dispatch or filesystem capability. Approval success means review completed,
not patch applied. No new package, dependency or manifest/lock change was needed.

## Files created

- `packages/agent_core/src/runveil_core/approvals.py`: strict proposal/request contracts.
- `packages/agent_core/tests/test_approval_domain.py`: meaningful input/digest boundaries.
- `packages/persistence/src/runveil_persistence/approvals.py`: transactional review workflow.
- `packages/persistence/migrations/versions/0009_approval_requests.py`: approval storage/guards.
- `packages/persistence/tests/test_approvals.py`: four database boundary scenarios.
- `apps/worker/src/runveil_worker/approvals.py`: demo, inspection and decision CLI.
- `docs/adr/0021-durable-patch-review.md`: scope and architectural decision.
- `docs/operations/APPROVALS.md`: usage and security/operational limits.
- `docs/operations/PHASE_6A.md`: this handoff.

## Files modified

- `packages/persistence/src/runveil_persistence/models.py`: approval mapping.
- `packages/persistence/tests/test_persistence.py`: add approval table to schema inventory.
- `README.md`, `ROADMAP.md`, `ARCHITECTURE.md`: current slice, scope and review gate.
- `docs/operations/DEVELOPMENT.md`, `docs/operations/PERSISTENCE.md`: operations links and migration boundary.

## Verification

Local Python 3.12.14, uv 0.12.19, Node 24.19.0, PostgreSQL 17.9. No live provider,
AWS or paid tests. CI itself was not run. The guide's commands were run locally.

The first default Compose instance inherited a different local PostgreSQL role;
connection attempts using the guide's `runveil` role failed before tests executed.
Used an isolated Compose project with explicit settings instead:

```sh
POSTGRES_USER=runveil POSTGRES_DB=runveil POSTGRES_PORT=54329 POSTGRES_PASSWORD=runveil-local-only docker compose -p runveil-phase6-checks up -d --wait --wait-timeout 90
export DATABASE_URL='postgresql+psycopg://runveil:runveil-local-only@127.0.0.1:54329/runveil'
export RUNVEIL_TEST_DATABASE_URL='postgresql+psycopg://runveil:runveil-local-only@127.0.0.1:54329/postgres'
export PATH=/Users/taom/.nvm/versions/node/v24.19.0/bin:$PATH
```

- `uv sync --locked --all-packages`, `npm ci`: passed. npm reported zero
  vulnerabilities and existing ESLint deprecation/optional install-script notices.
- `uv run alembic upgrade head`, `uv run alembic check`: passed through 0009,
  no metadata drift.
- `uv run pytest packages/persistence/tests/test_approvals.py packages/agent_core/tests/test_approval_domain.py -q --tb=short`:
  **5 passed**. Covers bounded proposal input, fresh-connection restoration,
  wrong digest, atomic rollback, rejection, cancellation, competing decisions,
  immutable storage, worker/profile refusal and populated migration/downgrade.
- `uv run ruff format --check .`, `uv run ruff check .`, `uv run mypy`: passed;
  80 files strictly typed.
- `uv run pytest -m 'not integration'`: **132 passed**, 130 deselected.
- `uv run pytest -m integration`: **129 passed, 1 failed**, 132 deselected.
  The sole failure was the old exact table inventory omitting `approval_requests`.
  After updating that assertion,
  `uv run pytest packages/persistence/tests/test_persistence.py::test_migration_round_trip_and_metadata -q`:
  **1 passed**, including full downgrade/upgrade and metadata constraint checks.
  Thus all 130 integration cases were verified across these runs; the whole suite
  was not repeated after this test-only correction.
- `uv run python scripts/phase5_acceptance.py`: passed both actual SIGKILL scenarios,
  clean checkpoint continuation, uncertain-intent failure, active-lease deferral,
  duplicate acknowledgement and disposable database cleanup.
- Separate subprocess CLI exercise via `uv run python -` ran `python -m
runveil_worker.approvals demo`, `inspect`, `approve` and `reject`. Both outcomes
  persisted across processes; repeated decisions returned exit 1 and the fixed
  `approval_failed` error. Every result asserted `patch_applied: false`.
- `npm run format:check`, `npm run lint`, `npm run typecheck`, `npm test`,
  `npm run build`: passed; one web test.
- `uv run python scripts/smoke.py`: passed with `DATABASE_URL` configured and
  unset (API/web health, production home page and corresponding readiness result).
- `git diff --check`: passed.

The Compose instances started for this session were stopped after verification;
volumes were retained. Integration and process-death harness databases clean up
themselves; the isolated development database retains the two CLI review examples.

## Remaining scope and recommended next slice

Phase 6 is not complete. No model-proposed request, durable worker approval resume,
patch writer, workspace proof, authenticated reviewer identity, HTTP API or UI is
claimed. Proposal text is retained review data; callers must exclude secrets.
The digest binds supplied text, not the real filesystem. Pending reviews may wait
indefinitely; cancellation makes them unresolvable. An approval here cannot be
reused as permission to mutate. Downgrade loses requests and is not run recovery.

Next, integrate one model-proposed replacement with durable worker approval
suspension/recovery and pinned workspace/preimage identity. Define single-use
execution and uncertain-effect recovery before enabling the controlled writer;
then add authenticated API/UI. Stop for review of this foundation first.
