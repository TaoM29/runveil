# Phase 4B handoff

Date: 2026-09-27. Implementation complete; stopped for review. No commit or push.

## Scope and decisions

Inspected the clean repository, root instructions, charter, architecture, roadmap,
accepted tool/runtime ADRs, completed Phase 4A code/tests/handoff, README and CI.
The user's Phase 4B request authorizes continuation past the preceding review stop.
Implemented the planned native repository read/search slice; worker/retry/approval
and mutation work remains outside this phase.

Recorded [ADR 0010](../adr/0010-repository-read-tools.md) before implementation.
Added a cohesive filesystem adapter package, `runveil_tools`, depending on core.
Core still owns grants, dispatch and the execution loop; no adapter import enters
core. The existing version-2 configuration and persistence schema remain valid.

- `repository.read_file` returns bounded UTF-8 character windows and a next offset.
- `repository.search` performs deterministic case-sensitive literal substring
  matching over an explicit sorted file allowlist, with bounded excerpts and
  explicit match truncation. No regex, shell or automatic directory discovery.
- Operator-selected root and exact file allowlist default to no file access. Both
  pinned and operator tool grants still apply. Hidden/noncanonical paths are
  rejected, and unlisted files fail before file I/O.
- Held directory descriptors anchor reads. Refuse symlinks, hard links, special
  files and cross-device paths; check the opened inode, file size and metadata.
  Root pathname replacement cannot redirect a binding. Close all owned descriptors.
- Whole files are limited to 64 KiB, search scans to 1 MiB, read responses to 4096
  characters and search to ten 160-character excerpts. Reject binary/NUL or invalid
  UTF-8 content. Failure never returns partial file/search content.
- Threaded I/O keeps the event loop responsive. Root duplication/close is locked;
  already-started work can finish cleanup after cancellation or binding close.
- Preserve only fixed enum codes from deliberate native errors. Unexpected handler
  exceptions remain generic. No OS error text or absolute root path is returned.
- Existing committed intent, provenance and atomic outcome/checkpoint/terminal
  transitions handle both success and file-policy denial. The offline demo now
  exercises model → search → model → read → model finish using a temporary public
  fixture; it never reads the developer's checkout.

## Files created

- `packages/tool_runtime/pyproject.toml`
- `packages/tool_runtime/src/runveil_tools/__init__.py`
- `packages/tool_runtime/src/runveil_tools/py.typed`
- `packages/tool_runtime/src/runveil_tools/filesystem.py`
- `packages/tool_runtime/src/runveil_tools/repository.py`
- `packages/tool_runtime/tests/test_repository.py`
- `docs/adr/0010-repository-read-tools.md`
- `docs/operations/REPOSITORY_TOOLS.md`
- `docs/operations/PHASE_4B.md`

## Files modified

- `packages/agent_core/src/runveil_core/tools.py`
- `packages/agent_core/tests/test_tools.py`
- `packages/persistence/tests/test_execution.py`
- `scripts/runtime_demo.py`
- `pyproject.toml`
- `uv.lock`
- `README.md`
- `ARCHITECTURE.md`
- `ROADMAP.md`
- `docs/operations/RUNTIME.md`

## Verification

Environment: macOS, Python 3.12.14, uv 0.12.19, Node 24.19.0, Docker PostgreSQL.
Used a new disposable Compose project and port, preserving existing services and
`.env`:

```sh
export PATH=/Users/taom/.nvm/versions/node/v24.19.0/bin:$PATH
POSTGRES_USER=runveil POSTGRES_PASSWORD=runveil-local-only POSTGRES_DB=runveil POSTGRES_PORT=55435 docker compose -p runveil-phase4b up -d --wait --wait-timeout 90
export DATABASE_URL='postgresql+psycopg://runveil:runveil-local-only@127.0.0.1:55435/runveil'
export RUNVEIL_TEST_DATABASE_URL='postgresql+psycopg://runveil:runveil-local-only@127.0.0.1:55435/postgres'
```

| Command                                                                                | Result                                                                 |
| -------------------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| `uv lock`                                                                              | Added only the workspace tool package; no external dependency upgrades |
| `uv sync --locked --all-packages`                                                      | Passed, including locked reinstall verification                        |
| `uv run ruff format --check .`                                                         | Passed                                                                 |
| `uv run ruff check .`                                                                  | Passed                                                                 |
| `uv run mypy`                                                                          | Passed; 48 source files                                                |
| `uv run pytest -m 'not integration'`                                                   | 121 passed                                                             |
| `uv run alembic upgrade head`                                                          | Passed on empty task database                                          |
| `uv run alembic check`                                                                 | No new upgrade operations detected                                     |
| `uv run pytest`                                                                        | 169 passed, including 48 PostgreSQL integration cases; no skips        |
| `uv run pytest packages/tool_runtime/tests`                                            | Eight passed after final inode precheck refinement                     |
| `uv run pytest packages/persistence/tests/test_execution.py -k repository_search_read` | Two passed after final inode precheck refinement                       |
| `uv run python scripts/runtime_demo.py`                                                | SUCCEEDED; five consumed steps; restored result verified               |
| `npm ci`                                                                               | Passed; zero audit vulnerabilities                                     |
| `npm run format:check`                                                                 | Passed                                                                 |
| `npm run lint`                                                                         | Passed                                                                 |
| `npm run typecheck`                                                                    | Passed                                                                 |
| `npm test`                                                                             | One web test passed                                                    |
| `npm run build`                                                                        | Production build passed                                                |
| `uv run python scripts/smoke.py`                                                       | API/web health, production page and readiness 200 passed               |
| `env -u DATABASE_URL uv run python scripts/smoke.py`                                   | API/web health, production page and readiness 503 passed               |
| Compose config and `SELECT 1` with variables above                                     | Passed                                                                 |
| `git diff --check`                                                                     | Passed                                                                 |

Seven focused filesystem test functions (eight cases) cover valid windows/Unicode,
literal search ordering/truncation, bounded JSON output, denied paths/files/grants,
links and special files, text/file/scan limits, root replacement and component swap,
concurrent file changes/growth, and cancellation descriptor cleanup. One existing
core case was extended to prove native error messages cannot leak through the safe
code boundary. Two persisted cases verify search/read provenance, restored context,
atomic success/failure and absence of denied file content/root paths from evidence.
Existing tool timeout, failure, concurrency and cancellation tests still pass.

Initial lint/type checks caught a constructed default argument and a test dictionary
variance issue; corrected before final checks. npm emitted its existing ESLint
deprecation and install-script notices. No hosted CI/Linux run or live/paid model
call was performed; CI continues to target Linux. The demo remains scripted.

Confirmed zero remaining randomly named integration databases. Removed only the
`runveil-phase4b` container, network and volume, including its disposable demo
record. The demo removed its temporary fixture directory, and smoke checks stopped
their application processes. Existing services and `.env` were preserved.

## Remaining concerns and next slice

This is a capability boundary for trusted native code and an operator-controlled
local checkout, not a hostile-code filesystem sandbox. Allowlisting a file does not
remove secrets or prompt injection from its contents. Approved file content enters
provider context and durable history; the operator must vet it.

Reads are live, not revision-pinned. Metadata checks detect ordinary changes, not
malicious local writers, concurrent directory relocation, privileged mount changes
or hard-link manipulation. Async cancellation cannot kill a hung filesystem syscall;
already-started reads may finish after the caller stops waiting. See
[repository operations](REPOSITORY_TOOLS.md) for supported limits and lifecycle.

Review Phase 4B, then begin the first coherent **Phase 5** slice: durable worker
ownership/claims, checkpoint resume and duplicate-delivery safety using scripted
model/fixture runs. Establish workspace/tool implementation identity before replaying
repository operations. Introduce queues, retries and budgets incrementally under
separate review gates. Keep controlled mutations, approvals and MCP in their phases.
