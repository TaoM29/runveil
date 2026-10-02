# Phase 10B handoff — durable sandbox test execution

Implemented 2026-10-02 from clean `03d3765` after the user authorized the next
Phase 10 slice. No commit or push. Stop for review after this slice.

## Implementation and decisions

Inspected the completed 10A runner, charter, architecture, roadmap and relevant
authorization, worker, elapsed-budget, repository recovery and approved-mutation
ADRs. Implemented the roadmap's next focused boundary: a pinned durable test profile,
not a complete coding application.

`python -m runveil_worker.sandbox_worker` submits/executes `sandbox-tests-v1`.
Configuration/checkpoint version 12 pins image/fixture/policy, local socket identity
and adapter/core implementation. `tests.run` requires empty arguments and explicit
pinned/operator EXECUTE grants. It runs only the public buggy clamp baseline. The
ordinary registry still refuses EXECUTE; approval/WRITE paths remain unchanged.

Existing intent, model provenance, budgets, checkpoints, ownership fences and
telemetry carry execution. Admission rechecks before create/start run outside
transactions. Container names derive from durable tool-call UUIDs. Clean checkpoints
resume without repeating results; unresolved intent terminates without constructing
a sandbox, accessing Docker or replaying execution. Bounded output/failure status
remain inspectable. A failed baseline is an observed test failure, not a repaired task.

The trace projection's supported checkpoint versions now include 12, preserving
accounting and final summaries for the new profile. No new API/UI, migration,
dependency or evaluator behavior. Historical reports remain unchanged; source
fingerprints naturally change and retain their conservative comparison/recovery guards.
[ADR 0033](../adr/0033-durable-sandbox-execution.md) records decisions and limits.

## Files created

- `packages/agent_core/src/runveil_core/sandbox.py`: closed identity/result contracts,
  narrow executor protocol, offer and intersected EXECUTE authorization.
- `packages/tool_runtime/src/runveil_tools/sandbox_execution.py`: verified image/socket/
  source binding, bounded observations and safe error conversion.
- `apps/worker/src/runveil_worker/sandbox_worker.py`: fixed profile, offline provider,
  submission/execution and terminal-only uncertain recovery CLI.
- `packages/persistence/tests/test_sandbox_worker.py`: five behavioral tests/eight
  collected cases; database-backed authorization, drift, checkpoint cuts, stale
  ownership, argument refusal, safe cleanup failures and opt-in real Docker worker.
- `docs/adr/0033-durable-sandbox-execution.md`: decision record.
- `docs/operations/PHASE_10B.md`: this handoff.
- `docs/operations/evidence/phase10b/boundary.json`: fresh 10A boundary acceptance.
- `docs/operations/evidence/phase10b/durable.json`: a fresh worker result, durable
  tool observation, trace projection and correlated JSON telemetry.

## Files modified

- `packages/agent_core/src/runveil_core/runtime.py`: version 12 and narrow execution branch.
- `packages/agent_core/src/runveil_core/tools.py`: fixed cleanup-uncertainty error code.
- `packages/persistence/src/runveil_persistence/execution.py`: require a verified
  sandbox/profile binding and keep review behavior restricted to versions 10/11.
- `packages/persistence/src/runveil_persistence/traces.py`: recognize checkpoint 12.
- `packages/tool_runtime/src/runveil_tools/sandbox.py`: optional durable invocation
  identity and pre-create/pre-start admission hooks; standalone behavior preserved.
- `.github/workflows/ci.yml`: opt-in real Docker worker check after image build.
- `README.md`, `ARCHITECTURE.md`, `ROADMAP.md`: implemented scope and next review gate.
- `docs/adr/0032-disposable-fixture-sandbox.md`: link to the explicit durable extension.
- `docs/operations/SANDBOX.md`, `WORKER.md`, `DEVELOPMENT.md`: usage, recovery and checks.

## Verification and evidence

Python 3.12.14, Node 24.19.0, local Docker Desktop 28.5.2/Linux ARM64. A dedicated
`runveil-phase10b` Compose project on port 55432 supplied PostgreSQL. All POSTGRES
settings were explicit; existing project credentials and data were not changed.

Commands run from the repository root:

```sh
export POSTGRES_USER=runveil POSTGRES_DB=runveil
export POSTGRES_PASSWORD=runveil-local-only POSTGRES_PORT=55432
docker compose -p runveil-phase10b up -d --wait --wait-timeout 90
export DATABASE_URL='postgresql+psycopg://runveil:runveil-local-only@127.0.0.1:55432/runveil'
export RUNVEIL_TEST_DATABASE_URL='postgresql+psycopg://runveil:runveil-local-only@127.0.0.1:55432/postgres'
uv run alembic upgrade head
uv run alembic check

uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest -m 'not integration'
uv run pytest packages/persistence/tests/test_sandbox_worker.py -k 'not real_docker'

docker build --network=none -t runveil-sandbox:phase10a sandbox
export RUNVEIL_SANDBOX_IMAGE=$(docker image inspect runveil-sandbox:phase10a --format '{{.Id}}')
uv run python scripts/phase10_sandbox_acceptance.py --image "$RUNVEIL_SANDBOX_IMAGE" --output /tmp/runveil-phase10b-boundary.json
uv run pytest packages/persistence/tests/test_sandbox_worker.py
uv run pytest packages/persistence/tests/test_sandbox_worker.py packages/persistence/tests/test_traces.py
uv run pytest packages/persistence/tests/test_sandbox_worker.py -k real_docker
uv run pytest
uv run python scripts/phase5_acceptance.py

npm run format:check
npm run lint
npm run typecheck
npm test
npm run build
uv run python scripts/smoke.py
git diff --check
```

Final result: **317 tests passed** with real Docker enabled (151 non-integration
and 166 integration cases), in 124.38 seconds. Ruff formatting/lint and strict mypy
passed. Alembic upgraded the fresh database and reported no schema drift. Frontend
lint/typecheck, all 11 tests, production build and API/web/readiness smoke passed.
Prettier and `git diff --check` passed. Phase 5 process-death acceptance passed both
checkpoint recovery and uncertain-intent failure, with active-lease deferral and
duplicate acknowledgement. No live provider or AWS calls.

Real Docker acceptance verified the unchanged isolation, timeout/output limits
and cancellation cleanup.
The real durable worker test uses a fresh process, checks persisted failed-test
output and container absence, and correlates its tool span with the durable UUID.
Trace checks verify version 12 accounting/final summary and no approval state.

The retained durable sample was submitted through `submit_sandbox`, executed with
`python -m runveil_worker.sandbox_worker work --allow-execute` in a fresh process
with JSON telemetry, then independently read through the tool record and trace
projection. Its report confirms the expected baseline failure and observed container
absence. The database is disposable; the retained JSON is evidence, not an execution
authority or a new evaluation artifact format.

Initial test setup used a macOS temporary path too long for Unix sockets; the stub
now uses a short owned temporary directory. One broad run had 316 passes and a real
Docker failure because a concurrent image rebuild removed its previously selected
local image ID. The image was held stable for subsequent checks. A new telemetry
assertion initially used SDK-prefixed keys; the existing JSON exporter intentionally
removes that prefix. The assertion was corrected and real Docker/telemetry passed.
No relaxation of runtime/image/authorization checks was needed for those failures.
The final full suite ran after both corrections and passed without skips.

Verification containers and this task's dedicated database volume were removed after
checks; no sandbox containers remain. The fixture image and retained JSON evidence
remain available for review. Existing project data was preserved.

## Remaining limits and recommended next slice

Phase 10 remains incomplete: no sandbox patching, persistent workspace, solved
coding task, hosted model or real model-quality evaluation. No remote CI execution
or independent AMD64 acceptance is claimed. The existing process-death acceptance
remains fixture-profile evidence; new sandbox recovery cuts are deterministic
interruptions at committed database boundaries, not a new SIGKILL experiment.

Database admission cannot atomically revoke a sent Docker request or a process
paused after its last check. Late outcomes cannot commit. The reviewed image and
trusted local daemon assumptions, watchdog, limits and manual orphan cleanup remain.
No cleanup reconciler or exactly-once claim. Unconfirmed/failed invocations require
exact-name inspection before concluding container resources are gone; budget and
ownership failures may take precedence over cleanup diagnostics. See operations.

Next: sandbox-bound fixture inspection and exact patch proposals with immutable
preimage/diff evidence and the existing human review boundary. Applying approved
patches and multi-task coding acceptance remain subsequent work. Stop for review.
