# Phase 4A handoff

Date: 2026-09-26. Implementation complete; stopped for review. No commit or push.

## Scope and decisions

Inspected the clean repository, instructions, charter, roadmap, architecture,
accepted ADRs, Phase 3 implementation/tests/handoff, README and CI. The user's
Phase 4 request authorizes continuation past Phase 3's review stop and supersedes
the original charter's historical Phase 0-only instruction.

Selected the roadmap's next coherent slice: typed registry and authorization
through the existing persisted runtime. Phase 4 is split into **4A dispatch/policy**
and **4B repository read/search**. The filesystem containment and disclosure
boundary deserves its own review; this slice creates no filesystem capability.
Recorded [ADR 0009](../adr/0009-typed-tool-dispatch.md) before implementing.

- Added typed native bindings, generated input/output schemas, strict validation,
  64 KiB input/output bounds, permissions, side-effect classes, cooperative async
  deadlines, fixed safe error codes and an explicit no-retry policy.
- Both pinned agent and operator grants must authorize the tool name and permission.
  Defaults deny access. Only READ with PURE/READ_ONLY is executable, regardless of
  grants for other classifications. Offers are filtered; dispatch checks again.
- Runtime configuration is version 2. Version 1 fails validation before lifecycle
  writes; existing versions/records/checkpoints remain unchanged and readable.
- Moved the public fixture into the registry. Persistence now records the selected
  tool name, retaining committed intent, same-run model provenance, atomic
  outcomes/checkpoints/terminal transitions and revision checks.
- Reused existing tool requested/completed/failed events. Intent does not claim
  actual dispatch; no synthetic tool-start event, worker or retry was introduced.
- Kept the implementation in core with the existing persistence adapter. No new
  dependency, package, migration or lockfile change was necessary.

## Files created

- `packages/agent_core/src/runveil_core/tools.py`
- `packages/agent_core/tests/test_tools.py`
- `docs/adr/0009-typed-tool-dispatch.md`
- `docs/operations/PHASE_4A.md`

## Files modified

- `packages/agent_core/src/runveil_core/runtime.py`
- `packages/persistence/src/runveil_persistence/execution.py`
- `packages/persistence/tests/test_execution.py`
- `scripts/runtime_demo.py`
- `docs/operations/RUNTIME.md`
- `README.md`
- `ARCHITECTURE.md`
- `ROADMAP.md`

## Verification

Environment: macOS, Python 3.12.14, uv 0.12.19, Node 24.19.0. Used a separate
Compose project/port with local example credentials, preserving existing services
and `.env`:

```sh
export PATH=/Users/taom/.nvm/versions/node/v24.19.0/bin:$PATH
POSTGRES_USER=runveil POSTGRES_PASSWORD=runveil-local-only POSTGRES_DB=runveil POSTGRES_PORT=55434 docker compose -p runveil-phase4a up -d --wait --wait-timeout 90
export DATABASE_URL='postgresql+psycopg://runveil:runveil-local-only@127.0.0.1:55434/runveil'
export RUNVEIL_TEST_DATABASE_URL='postgresql+psycopg://runveil:runveil-local-only@127.0.0.1:55434/postgres'
```

| Command                                              | Result                                                          |
| ---------------------------------------------------- | --------------------------------------------------------------- |
| `uv sync --locked --all-packages`                    | Passed; unchanged dependencies                                  |
| `uv run ruff format --check .`                       | Passed                                                          |
| `uv run ruff check .`                                | Passed                                                          |
| `uv run mypy`                                        | Passed; 44 source files                                         |
| `uv run pytest -m 'not integration'`                 | 112 passed                                                      |
| `uv run alembic upgrade head`                        | Passed on empty task database                                   |
| `uv run alembic check`                               | No new upgrade operations detected                              |
| `uv run pytest`                                      | 158 passed, including 46 PostgreSQL integration cases; no skips |
| `uv run python scripts/runtime_demo.py`              | SUCCEEDED, three consumed steps; restored result verified       |
| `npm ci`                                             | Passed; zero audit vulnerabilities                              |
| `npm run format:check`                               | Passed                                                          |
| `npm run lint`                                       | Passed                                                          |
| `npm run typecheck`                                  | Passed                                                          |
| `npm test`                                           | One web test passed                                             |
| `npm run build`                                      | Production build passed                                         |
| `uv run python scripts/smoke.py`                     | API/web health, production page, readiness 200 passed           |
| `env -u DATABASE_URL uv run python scripts/smoke.py` | API/web health, production page, readiness 503 passed           |
| Compose config and `SELECT 1` with variables above   | Passed                                                          |
| `git diff --check`                                   | Passed                                                          |

Four focused unit test functions (10 cases) cover successful dispatch, strict
arguments, schema isolation, duplicate registration, both grant ceilings,
unsupported permissions/side effects, missing tools, malformed/oversized output,
handler failure, timeout, cancellation and no retries. Integration coverage adds
an unadvertised denied call, a different registered name with committed/unlocked
intent and atomic success/failure outcomes, and extends the existing concurrency
checks to tool execution. Late tool results cannot overwrite cancellation or
competing history; task cancellation preserves unresolved intent. Existing tests
continue to verify fixture arguments, step bounds and historical reconstruction.

Initial lint checks caught import ordering and an unused metadata-validation
expression; both were corrected. npm emitted existing ESLint deprecation and
install-script notices. No hosted CI or live/paid provider invocation was run.
The demo remains entirely scripted and is not new hosted acceptance evidence.

Confirmed zero remaining randomly named integration databases. Removed only the
`runveil-phase4a` container, network and volume after verification, including its
disposable demo record. Existing services and `.env` were preserved. Smoke checks
stopped their own application processes.

## Limitations and next slice

Handlers and their classifications are trusted native code. Async deadlines are
cooperative, not process isolation. The registry provides no filesystem, shell or
network sandbox. Task interruption still leaves RUNNING/REQUESTED records; durable
recovery and implementation-version pinning before replay remain future work.
Valid model arguments and approved outputs are persisted; callers must exclude
sensitive data. Safe error mapping does not redact arbitrary valid content.

Review this slice, then implement **Phase 4B: repository read/search tools** through
this path, with explicit repository root/file disclosure policy, symlink/path
containment, bounded content/search results and boundary tests. Phase 4 remains
incomplete until that slice is implemented and reviewed. Worker reliability,
mutations, approvals and MCP remain in their planned phases.
