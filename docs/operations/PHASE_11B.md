# Phase 11B handoff: pinned read-only MCP worker

Date: 2026-10-02. Implemented; review pending. No commit or push.

## Implementation and decisions

Added `mcp-fixture-read-v1`, a fixed public stdio server profile with immutable
interpreter/server/contract/implementation identity and version-17 configuration
and checkpoints. Clean work requires its own READ grant and a matching deployment.
The native registry, typed contracts, dual policy grants, budgets, persisted
intent/outcomes and telemetry remain the execution path. The trace reader now
projects v17 accounting. MCP has no mutation or approval capability.

Server launch is lazy, after durable intent; ownership/history/deadline fences
precede launch and the post-discovery RPC. Source is captured before configuration
verification and executed in isolated Python mode with fixed directory and blanked
SDK-inherited environment. Clean checkpoints resume from durable context, never
repeating a committed read. Uncertain model/tool intent, including a remote result
lost before persistence, fails without constructing a binding, launching a server,
requiring a READ grant or replaying. Existing elapsed expiry still takes precedence.

The one-hour run deadline deliberately exceeds the existing 660-second lease;
otherwise real process recovery after lease expiry would always be overdue.
Three steps, two model calls, one tool call and a ten-second tool deadline keep the
fixture bounded. No migrations, new dependencies, broker path, generic server
configuration, HTTP transport or approval changes. See
[ADR 0041](../adr/0041-pinned-mcp-worker.md) and [operations](MCP.md).

## Files created

- `packages/agent_core/src/runveil_core/mcp.py`: profile identity and read policy.
- `packages/tool_runtime/src/runveil_tools/mcp_fixture.py`: fixed public server.
- `packages/tool_runtime/src/runveil_tools/mcp_execution.py`: captured source,
  implementation identity and lazy typed binding.
- `apps/worker/src/runveil_worker/mcp_worker.py`: submission, claimed execution,
  recovery selection, admission checks and local CLI.
- `packages/persistence/tests/test_mcp_worker.py`: eight integration cases.
- `docs/adr/0041-pinned-mcp-worker.md`: architectural decisions and limits.
- `docs/operations/PHASE_11B.md`: this handoff.

## Files modified

- `packages/agent_core/src/runveil_core/runtime.py`: v17 identity/policy validation
  and checkpoint acceptance; no new dispatch loop or retry logic.
- `packages/persistence/src/runveil_persistence/execution.py`: require verified
  configuration and dedicated claim for MCP-bound runs.
- `packages/persistence/src/runveil_persistence/traces.py`: recognize v17.
- `ARCHITECTURE.md`, `ROADMAP.md`, `docs/operations/MCP.md`,
  `docs/operations/WORKER.md`: implemented scope, commands and review gate.

## Verification

Used native Python 3.12.14 in the existing `/tmp/runveil-phase11-venv` via
`UV_PROJECT_ENVIRONMENT=/tmp/runveil-phase11-venv`, and Node 24.19.0 with
`/Users/taom/.nvm/versions/node/v24.19.0/bin` prepended to `PATH`. The isolated
Compose project `runveil-phase11b` used explicit `POSTGRES_USER=runveil`,
`POSTGRES_DB=runveil`, the documented local-only password and `POSTGRES_PORT=55412`.
`DATABASE_URL` selected its `runveil` database; `RUNVEIL_TEST_DATABASE_URL` selected
its `postgres` administration database. No existing database was reset or changed.

Commands and results:

- `uv sync --locked --all-packages`: passed, unchanged lockfile.
- `uv run ruff format --check .`: passed, 281 Python files.
- `uv run ruff check .`: passed.
- `uv run mypy`: passed, 148 source files.
- `uv run pytest packages/persistence/tests/test_mcp_worker.py -q --tb=short`:
  eight passed after fixing the trace projection's version limit.
- `uv run pytest -q --tb=short`: 376 passed, 11 Docker-opt-in cases skipped;
  all skipped cases passed in the separate Docker run below.
- `uv run alembic upgrade head` and `uv run alembic check`: passed; no new operations.
- `uv run python -m runveil_worker.mcp_worker submit`, then
  `RUNVEIL_TELEMETRY=json uv run python -m runveil_worker.mcp_worker work --run-id <returned-id> --allow-read`:
  passed with the real SDK server, durable result and JSON model/tool/root telemetry.
- `uv run python scripts/phase5_acceptance.py`: passed both real SIGKILL cases,
  active-lease deferral, duplicate acknowledgement and database cleanup.
- `npm run lint`, `npm run typecheck`, `npm test`, `npm run build`: passed;
  13 frontend tests across six files.
- `uv run python scripts/smoke.py`: passed API/web health, showcase/operator routes,
  framing/referrer protections and database readiness.
- `npm run format:check` and `git diff --check`: passed.

The first full suite overlapped the deadline/source change; two fresh-process
recovery cases correctly refused the changed identity. The complete suite was
restarted after freezing implementation source. No recovery check was weakened.

Docker regression commands:

```sh
docker build --network=none -t runveil-sandbox:phase11b-verification sandbox
RUNVEIL_PHASE11B_IMAGE=$(docker image inspect runveil-sandbox:phase11b-verification --format '{{.Id}}')
uv run python scripts/phase10_sandbox_acceptance.py --image "$RUNVEIL_PHASE11B_IMAGE" --output /tmp/runveil-phase11b-sandbox-acceptance.json
RUNVEIL_SANDBOX_IMAGE="$RUNVEIL_PHASE11B_IMAGE" uv run pytest packages/persistence/tests/test_sandbox_worker.py packages/persistence/tests/test_sandbox_review.py packages/persistence/tests/test_sandbox_patch_worker.py packages/persistence/tests/test_software_worker.py -k real_docker -q --tb=short
```

The image build and sandbox boundary acceptance passed. Docker tests: 11 passed,
39 deselected. Across both runs, all 387 Python cases passed. These are regression
checks for the existing sandbox, not a claim that the MCP server is sandboxed.
The temporary Compose project/database and verification image tag were removed
after checks. Demonstration runs in that disposable database are not retained
product evidence; no pre-existing volume was removed.

## Evidence and limits

The eight new cases cover both grants/store guards and four identity drift fields
at a clean checkpoint; fresh-process recovery after model/tool checkpoints;
interruption at model/tool intent and after an actual remote response; active and
terminal duplicate selection; and ownership loss during discovery/after response.
They verify durable provenance, restored state, trace accounting and span IDs.
Failure-only recovery is tested with binding construction made impossible.

MCP cut points use deterministic cancellation fault injection; there is no new
MCP-specific SIGKILL harness. Actual process-death regression is the existing Phase
5 acceptance command. Native MCP worker execution was checked on macOS; Docker
Linux checks cover the existing sandbox. Live hosted models, AWS and external MCP
services were not used. No frontend changes or new browser-interaction claims.

Identity is conservative compatibility evidence, not full dependency attestation
or protection against concurrent installation changes. Keep source/interpreter
stable during execution. Stdio still runs trusted host code, and SDK decoding
precedes size checks. Admission fencing cannot revoke an already-started RPC;
uncertain outcomes fail without replay. Configuration rejection/missing grants
leave the existing lease until expiry. Fixed public server only; other servers
require a separately reviewed profile.

## Recommended next slice

Review Phase 11B, then audit Phase 11 acceptance and remaining trust/SDK limitations
against the charter before proposing further scope. Stop here for review.
