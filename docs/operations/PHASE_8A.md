# Phase 8A handoff — deterministic evaluation foundation

Implemented on 2026-10-01 after inspection of the clean working tree at `ad2e5ff`,
Phase 7 closure/implementation, charter, roadmap, architecture, accepted execution,
repository, trace and telemetry boundaries, development guide and CI. Phase 8
continuation was explicitly authorized. No commit or push was made.

## Implementation and decisions

The new evaluator runs a versioned three-case public code-reading calibration
through the existing core and PostgreSQL execution store. Dedicated existing job
claims preserve elapsed/token/cost/call budgets and transactional fences. Two
immutable versions differ only in their three/five-step budgets. A fresh scripted
provider and private one-file directory isolate every case; only existing read/search
tools are available. No production runtime, API, UI or permission logic changed.

Deterministic scoring reconstructs committed terminal evidence in a read-only
consistent transaction. It requires successful completion, exact summary and exact
ordered successful tools. Failures stay in the denominator. The comparison rejects
changed suite/implementation digests, missing/reordered cases and reused executions.
Local EvalRun/EvalCaseResult snapshots contain full benchmark/configuration provenance,
source/dependency identity, timestamps, durable run IDs, safe grades and accounting.

[ADR 0029](../adr/0029-offline-evaluation-harness.md) records the important trade-off:
local report artifacts establish the harness before adding evaluation persistence
or scheduling. Scripts contain answers; these results do not measure model quality.
No arbitrary code execution is introduced to satisfy a later coding benchmark.

## Files created

- `packages/evaluations/pyproject.toml`
- `packages/evaluations/src/runveil_evaluations/{__init__.py,__main__.py,contracts.py,fixtures.py,runner.py,py.typed}`
- `packages/evaluations/tests/test_contracts.py`
- `packages/persistence/tests/test_evaluations.py`
- `docs/adr/0029-offline-evaluation-harness.md`
- `docs/operations/EVALUATIONS.md`
- `docs/operations/PHASE_8A.md`
- `docs/operations/evidence/phase8/calibration.json`

## Files modified

- `pyproject.toml`, `uv.lock`: workspace package and test discovery, with no new
  third-party dependency/version changes.
- `ARCHITECTURE.md`: current implementation heading and evaluation boundary.
- `ROADMAP.md`: Phase 7 continuation and focused 8A review gate; full Phase 8 remains open.
- `docs/operations/DEVELOPMENT.md`: evaluation operations link.

The original charter remains unchanged. The new tests run through existing CI;
no additional workflow or broad test matrix was added.

## Verification

Commands ran from the repository root using Python 3.12.14, uv 0.12.19 and Node
24.19.0. Database checks used a task-owned Compose project `runveil-phase8` on
loopback port 55438, with explicit public local-only credentials, user/database
`runveil`, and `--env-file /dev/null`. No existing database was reset. The task-owned database/container/volume were
removed after verification; the retained JSON is the review artifact, so its run
IDs will not resolve after cleanup. Reproduction creates fresh IDs.

```sh
uv lock
uv sync --locked --all-packages
npm ci
export POSTGRES_USER=runveil POSTGRES_DB=runveil
export POSTGRES_PASSWORD=runveil-local-only POSTGRES_PORT=55438
docker compose --env-file /dev/null -p runveil-phase8 config --quiet
docker compose --env-file /dev/null -p runveil-phase8 up -d --wait --wait-timeout 90
export DATABASE_URL='postgresql+psycopg://runveil:runveil-local-only@127.0.0.1:55438/runveil'
export RUNVEIL_TEST_DATABASE_URL='postgresql+psycopg://runveil:runveil-local-only@127.0.0.1:55438/postgres'
uv run alembic upgrade head
uv run alembic check
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest --tb=short
uv run python scripts/phase5_acceptance.py
npm run format:check
npm run lint
npm run typecheck
npm test
npm run build
uv run python scripts/smoke.py
uv run python -m runveil_evaluations --output docs/operations/evidence/phase8/calibration.json
git diff --check
```

Results: locked installation and migrations passed; Alembic reported no pending
schema operations. Ruff format/lint and strict mypy passed (110 source files).
The complete Python suite passed **296 tests**, including PostgreSQL integration,
in 84.68 seconds. The separate process-death acceptance passed checkpoint recovery,
uncertain-intent failure and duplicate acknowledgement. Frontend formatting, lint,
types, **11 tests**, production build and real HTTP smoke checks all passed.
No hosted provider, AWS or new browser interaction was required for this backend-only
slice. Existing Phase 7 browser acceptance remains the UI evidence.

The three added tests cover content identity/immutability, repeated real-database
comparison with raw invocation counts and immutable-version reconciliation, rescore
identity checks, incompatible comparisons and oracle/tool-boundary failures.
The negative mutation request is rejected as `invalid_response` before any tool
intent; traversal records `invalid_tool_arguments`. No per-case test proliferation.

The [retained CLI report](evidence/phase8/calibration.json) records **2/3 → 3/3**,
7 → 9 consumed steps, 5 → 6 model calls and 2 → 3 tool calls. Baseline's final
case fails with `step_limit_exceeded`; candidate passes all cases. Candidate
accounting is 60 input/30 output synthetic tokens and 120,000 nano-USD under the
synthetic tariff, with zero unknown attempts. Repeating the CLI against the same
output path exits one, preserves the report and does not create another batch.

During development, the first isolated database setup had a local configuration
mismatch; recreating only the task-owned volume with explicit user/database settings
resolved it. Focused checks then exposed the existing requirement for claimed
execution with elapsed budgets; the adapter was corrected to use that fence.
The refused mutation assertion was corrected to the earlier model-validation
boundary. These were resolved before final verification.

## Remaining limits and next slice

This is 8A, not full Phase 8 acceptance. The approximately 20–30 controlled coding
cases, held-out discipline and broader version/provider selection remain open.
The fixed CLI has no dynamic grader, generated-code execution, hosted calls,
resumable batches, evaluation database schema or UI. Statistics remain Phase 9.

Reports are local artifacts, not attestations. Interrupted output can be empty or
partial; committed run history remains authoritative and is never silently retried.
The dedicated profile has no polling/resume entry point; temporary fixtures disappear
after each case. IDs/timestamps/elapsed times vary. The implementation fingerprint
is conservative and not an environment/container digest. Existing security,
approval, observability and recovery limitations remain as documented.

Next: review 8A, then expand the versioned controlled benchmark toward 20–30 cases
with meaningful deterministic read-only oracles and explicit development/held-out
separation. Keep sandbox-dependent mutation/test execution a separate planned slice.
Stop for review; no automatic continuation is authorized.
