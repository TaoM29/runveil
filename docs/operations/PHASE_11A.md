# Phase 11A handoff: typed read-only MCP

Date: 2026-10-02. Implemented, awaiting review. No commit or push.

## Implementation

The official MCP Python SDK now connects a trusted local stdio server to existing
Runveil typed read tools. Capability discovery and a bounded complete catalog precede
explicit operator selection. Selected schemas must match local Pydantic contracts.
Local names/descriptions and READ/READ_ONLY classification are operator-owned;
server annotations confer no permission. Native dual grants, validation, deadlines,
durable intent/outcome/checkpoint writes and payload-free telemetry remain in force.

The executable demo persists a complete scripted run against a real offline SDK
server. Focused tests cover protocol errors, invalid/oversized output, disconnect,
timeout/cancellation, schema drift, discovery pagination, wire-log redaction,
expired bindings and the existing registry's two grants. Three PostgreSQL cases
verify success, safe failure and interruption after a remote response, including
committed intent outside transactions, provenance, restored outcomes, trace/span
correlation and refusal to replay.

## Files created

- `packages/tool_runtime/src/runveil_tools/mcp.py`: session-scoped adapter.
- `packages/tool_runtime/tests/test_mcp.py`: real stdio boundary tests.
- `packages/persistence/tests/test_mcp_execution.py`: durable integration tests.
- `scripts/mcp_fixture_server.py`: public fixture and explicit test fault modes.
- `scripts/mcp_demo.py`: persisted runtime demonstration with optional telemetry.
- `docs/adr/0040-typed-read-only-mcp.md`: decisions and trust limits.
- `docs/operations/MCP.md`: operation, embedding and verification instructions.
- `docs/operations/PHASE_11A.md`: this handoff.

## Files modified

- `packages/tool_runtime/pyproject.toml` and `uv.lock`: official SDK `>=1.30,<2`,
  locked to 1.30.0, plus its supporting dependencies.
- `ARCHITECTURE.md`: implemented MCP boundary and diagram; corrected stale heading.
- `ROADMAP.md`: 11A scope/review gate; corrected the stale Phase 10 table row to 10G.
- `docs/operations/DEVELOPMENT.md`: link to MCP operations.

No core/persistence implementation, database migration, runtime configuration,
approval workflow, frontend or existing worker profile changed. The original
charter remains unchanged. Current user authorization advances Phase 11 without
claiming human acceptance of earlier Phase 10/showcase work.

## Decisions and remaining limits

See [ADR 0040](../adr/0040-typed-read-only-mcp.md). Exact schema mapping deliberately
avoids an arbitrary-schema interpreter. Only structured JSON results are supported.
The SDK's maintained v1 API is explicitly bounded below 2; an SDK major upgrade
requires compatibility review.

Stdio executes trusted host code; it does not enforce a server's read-only claim.
Wire data is decoded before payload limits are checked. No adversarial-server
isolation, HTTP transport, MCP mutation or generic approval mapping is claimed.
Existing exact patch approvals cannot authorize MCP calls. The in-process demo
does not enroll workers or pin executable identity for recovery. An interrupted
run stays inspectable and is not automatically resumed or replayed.

## Verification environment

The existing Intel Python environment on this ARM Mac could not build the newest
transitive `cryptography` package with the ARM-only system toolchain. No dependency
downgrade was used. Installed native CPython 3.12.14 with:

```sh
uv python install cpython-3.12-macos-aarch64-none
UV_PROJECT_ENVIRONMENT=/tmp/runveil-phase11-venv uv add --package runveil-tool-runtime 'mcp>=1.30,<2' --python /Users/taom/.local/share/uv/python/cpython-3.12.14-macos-aarch64-none/bin/python3.12
```

All following Python checks used `UV_PROJECT_ENVIRONMENT=/tmp/runveil-phase11-venv`.
Frontend commands used Node 24.19.0 by prepending
`/Users/taom/.nvm/versions/node/v24.19.0/bin` to `PATH`.

Initial database attempts failed authentication because local Compose configuration
selected a different user. No existing database credentials or volume were changed.
Verification used an isolated `runveil-phase11` Compose project with explicit
`POSTGRES_USER=runveil`, `POSTGRES_DB=runveil`, the documented local-only password
and `POSTGRES_PORT=55411`. `DATABASE_URL` named its `runveil` database;
`RUNVEIL_TEST_DATABASE_URL` named its `postgres` database. Tests and process-death
acceptance created and removed their own temporary databases. The demo run was
also in this disposable environment, not retained product evidence.

## Commands and results

- `uv sync --locked --all-packages`: passed; 74 resolved packages.
- `uv run ruff format --check .`: passed, 274 Python files.
- `uv run ruff check .`: passed.
- `uv run mypy`: passed, 143 source files. Only the SDK's untyped server decorators
  need narrowly coded ignores; project handlers remain strictly annotated.
- `uv run pytest packages/tool_runtime/tests/test_mcp.py -q`: initial seven cases
  passed; two discovery/log cases added and verified by the final full suite.
- `uv run pytest packages/persistence/tests/test_mcp_execution.py -q --tb=short`:
  all three cases passed after the isolated database setup was corrected.
- `uv run pytest -q --tb=short`: 368 passed, 11 Docker-opt-in cases skipped.
- `uv run alembic upgrade head` and `uv run alembic check`: passed; no new operations.
- `RUNVEIL_TELEMETRY=json uv run python scripts/mcp_demo.py`: succeeded in three
  steps, emitted the existing root/model/tool JSON spans and restored the checkpoint.
- `uv run python scripts/phase5_acceptance.py`: passed both actual SIGKILL recovery
  cases, lease deferral, duplicate acknowledgement and temporary database cleanup.
- `npm run lint`, `npm run typecheck`, `npm test`, `npm run build`: passed;
  six frontend test files, 13 tests.
- `npm run format:check` and `git diff --check`: passed.
- `uv run python scripts/smoke.py`: passed API/web health, product/operator routes,
  framing/referrer protections and database readiness.

Docker verification uses the current fixed image built with:

```sh
docker build --network=none -t runveil-sandbox:phase11-verification sandbox
RUNVEIL_PHASE11_IMAGE=$(docker image inspect runveil-sandbox:phase11-verification --format '{{.Id}}')
uv run python scripts/phase10_sandbox_acceptance.py --image "$RUNVEIL_PHASE11_IMAGE" --output /tmp/runveil-phase11-sandbox-acceptance.json
RUNVEIL_SANDBOX_IMAGE="$RUNVEIL_PHASE11_IMAGE" uv run pytest packages/persistence/tests/test_sandbox_worker.py packages/persistence/tests/test_sandbox_review.py packages/persistence/tests/test_sandbox_patch_worker.py packages/persistence/tests/test_software_worker.py -k real_docker -q --tb=short
```

The image build and sandbox boundary acceptance passed. Docker integration:
11 passed, 39 deselected. This exercises all 11 cases skipped by the initial full
suite, for 379 Python cases passed across the two runs. The temporary Compose
project/database and verification image tag were removed after verification;
the pre-existing default database volume was preserved.

No live model, AWS or remote MCP service was contacted for acceptance. No UI change
was made, so this slice adds no browser interaction acceptance requirement.

## Recommended next slice

After review, define one pinned read-only MCP worker profile, including executable
and contract identity, clean-checkpoint recovery and uncertain-intent refusal.
Do not extend transport or mutation scope automatically.
