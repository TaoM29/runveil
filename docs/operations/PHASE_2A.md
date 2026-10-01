# Phase 2A handoff

Date: 2026-09-26. Implemented and stopped for review. No commit or push.

## Implementation summary and scope

Inspected the clean repository, root AGENTS instructions, charter, architecture,
roadmap, accepted ADRs, Phase 1 core/persistence implementation, migrations,
invocation tests, prior handoff, README and CI. The preserved charter's original
Phase 0-only instruction is historical; the current request authorizes Phase 2.
The roadmap explicitly recommends contracts/actions/scripted provider first, then
the hosted adapter. This implements that coherent **Phase 2A** review slice; it
does not claim the entire Phase 2 acceptance gate is met.

Added strict versioned model request/response contracts, normalized usage/latency,
an async provider protocol, a JSON action schema and structured action validation.
The deterministic scripted provider returns ordered detached fixtures or fixed
error codes and captures detached requests. It has no network, sleeps or retries.
Four test functions (14 cases) cover the contracts and validation; one PostgreSQL
integration test verifies committed request, out-of-transaction provider call,
validated response persistence and checkpoint restoration. Existing Phase 1 tests
continue to pass. No execution loop, new package, migration, HTTP route or UI was
added. Pydantic is now a direct core dependency, using the already locked version.

## Key decisions

See [ADR 0006](../adr/0006-model-contracts.md) and [usage](MODELS.md).

- Keep contracts and the small scripted provider in the existing core package.
  Introduce an adapter package when real provider transport creates a useful boundary.
- Use one structured action envelope, either `tool_call` or `finish`. Unknown
  fields, malformed/duplicate-key/non-finite JSON, invalid types, incomplete output
  and unadvertised tool names fail without automatic output repair.
- Normalize errors to fixed codes; suppress raw validation details for invalid
  model content. Do not infer retry policy. Unknown token counts remain null.
- Separate generation and action validation. Advertised tool membership is not
  authorization, and argument-schema enforcement belongs in Phase 4.
- Keep credentials/transport configuration outside persistable model payloads.
  Contracts freeze assignments but JSON leaves remain caller-owned; retained
  scripted fixtures/history and persistence data are detached at serialization.
- Reuse opaque Phase 1C JSON fields without interpreting or migrating old records.
  Contract restoration is explicit and rejects unsupported versions.

## Verification commands and results

Environment: macOS, Python 3.12.14, uv 0.12.19, Node 24.19.0 (selected explicitly),
Docker PostgreSQL. Used only a task-specific Compose project and local fixture data:

```sh
export PATH="$HOME/.nvm/versions/node/v24.19.0/bin:$PATH"
POSTGRES_USER=runveil POSTGRES_PASSWORD=runveil-local-only POSTGRES_DB=runveil POSTGRES_PORT=55432 docker compose -p runveil-phase2a up -d --wait --wait-timeout 90
export DATABASE_URL='postgresql+psycopg://runveil:runveil-local-only@127.0.0.1:55432/runveil'
export RUNVEIL_TEST_DATABASE_URL='postgresql+psycopg://runveil:runveil-local-only@127.0.0.1:55432/postgres'
```

| Command                                                                 | Result                                                               |
| ----------------------------------------------------------------------- | -------------------------------------------------------------------- |
| `uv lock`                                                               | Updated only the core's Pydantic dependency edge; no version changes |
| `uv sync --locked --all-packages`                                       | Passed                                                               |
| `uv run ruff format --check .`                                          | Passed                                                               |
| `uv run ruff check .`                                                   | Passed                                                               |
| `uv run mypy`                                                           | Passed; 33 source files                                              |
| `uv run pytest -m 'not integration'`                                    | 87 passed; 22 integration tests deselected                           |
| `uv run pytest -m integration`                                          | 22 passed; 87 other tests deselected; no skips                       |
| `uv run alembic upgrade head`                                           | Passed on empty task database                                        |
| `uv run alembic check`                                                  | No new upgrade operations detected                                   |
| `docker compose -p runveil-phase2a config --quiet` with variables above | Passed                                                               |
| `npm ci`                                                                | Passed; zero audit vulnerabilities                                   |
| `npm run format:check`                                                  | Passed                                                               |
| `npm run lint`                                                          | Passed                                                               |
| `npm run typecheck`                                                     | Passed                                                               |
| `npm test`                                                              | One web test passed                                                  |
| `npm run build`                                                         | Production build passed                                              |
| `uv run python scripts/smoke.py` with database URL                      | API/web liveness, page and readiness 200 passed                      |
| `env -u DATABASE_URL uv run python scripts/smoke.py`                    | API/web liveness, page and readiness 503 passed                      |
| `git diff --check`                                                      | Passed                                                               |

Initial checks caught forward annotations, a missing TypeAdapter annotation, an
exception-test assertion that incorrectly required suppressed context even where
no exception was wrapped, and formatting in the new documentation example. Fixed
before the final passing checks. npm reported the existing ESLint deprecation and
install-script policy notices; frontend dependencies were unchanged. No hosted
CI or live/paid provider call was run. CI already discovers the added tests.

Confirmed zero remaining `runveil_test_*` databases. Removed only this task's
`runveil-phase2a` container, network and volume with the same Compose variables and
`docker compose -p runveil-phase2a down --volumes`. Existing services/data and
local `.env` were preserved. Smoke servers stopped themselves.

## Files created

- `docs/adr/0006-model-contracts.md`
- `docs/operations/MODELS.md`
- `docs/operations/PHASE_2A.md`
- `packages/agent_core/src/runveil_core/models.py`
- `packages/agent_core/src/runveil_core/scripted.py`
- `packages/agent_core/tests/test_models.py`

## Files modified

- `ARCHITECTURE.md`
- `README.md`
- `ROADMAP.md`
- `docs/operations/PERSISTENCE.md`
- `packages/agent_core/pyproject.toml`
- `packages/persistence/tests/test_invocations.py`
- `uv.lock`

## Remaining concerns and recommended next slice

**Phase 2B: hosted/OpenAI-compatible adapter**, offline adapter contract tests,
actual timeout/cancellation and error mapping, and an explicitly opt-in minimal
live structured invocation. Validate provider capabilities and supported schema
translation in that slice. Full Phase 2 acceptance requires that real invocation;
there is no hosted provider yet.

The script simulates timing/errors and must have one ordered consumer for
reproducibility. It does not exercise real timeout/cancellation or networking.
Contract bounds are not aggregate request-byte or token budgets. Input schemas
are only JSON objects; tool argument validation, authorization and execution are
unimplemented. Artifact references are inert strings. There is no automatic
redaction: callers must select safe content before storage. Runtime orchestration,
worker ownership, recovery, retries and side-effect safety remain later phases.
