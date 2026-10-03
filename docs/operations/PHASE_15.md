# Phase 15 local security detour

Date: 2026-10-03. Temporary local-only slices; review pending. Phase 12C remains
paused and Phase 12 is not closed. No AWS acceptance or deployment is part of this
work. The initial implementation stopped uncommitted for review; the owner then
explicitly authorized splitting the changes into commits and pushing them.

## 15A: threat model and abuse analysis

Completed repository/authority inspection before implementation. Preserved the
pre-existing ROADMAP changes and untracked Phase 12C preflight record, then recorded
the owner's pause and temporary sequence in ROADMAP, ARCHITECTURE, the 12C record
and ADR 0044. The original charter is retained unchanged; ADR 0044 supplements its
Phase 15 scope and sequence.

The [threat model](../security/THREAT_MODEL.md) covers attack paths, existing controls,
residual risks and dispositions for repository injection, arguments, filesystem,
commands, authorization, secrets, SSRF/network, resource use, duplicate effects,
sandbox assumptions, telemetry and public evidence. Selected local work is finite
telemetry metadata enforcement before tracer handoff plus a durable hostile-file
regression. Existing path/sandbox/approval/budget tests are reused.

## 15B: local hardening

Implemented finite telemetry metadata validation in core before a supplied tracer
receives attributes. The worker exporter reapplies the same policy, preserving
independent export filtering without duplicate validation branches. Unexpected
fields, invalid UUIDs/outcomes, booleans in counters, negative counters and counters
above signed 64-bit range are omitted. A malformed UUID no longer discards the
rest of a safe span/batch. No payload redactor, schema migration, dependency change
or runtime authority was introduced.

A real SDK in-memory sink test first reproduced the disclosure, then passed after
the fix. An existing exporter integration test now also checks that malformed IDs
cannot leak or suppress valid accounting. A three-case durable runtime regression
feeds hostile README content to a deliberately compliant scripted provider: private
file access, traversal and a registered but unauthorized shell tool all fail with
safe persisted outcomes. The test verifies actual tool-role content, unchanged
offers, invocation history and absence of undisclosed file contents.

The initial local gates passed: strict typing, 168 non-integration tests and 216
PostgreSQL integration tests. The eleven opt-in Docker cases are verified separately
below. Existing authorization, path, approval, recovery, budgets, provider and MCP
tests supply broader abuse evidence without adding duplicate tests for each threat.

The requested cleanup removed duplicated worker telemetry policy and an ignored
Finder `.DS_Store` file. Inspected source comments mostly explain security,
concurrency or recovery constraints; no redundant helper-comment blocks or clearly
unused application files were found in the reviewed paths. Retained historical
ADRs/handoffs supply review evidence and are not treated as disposable clutter.

## 15C: public-demo safety model

The [public-demo model](../security/PUBLIC_DEMO.md) defines anonymous read-only
inspection, local operator fixture execution and prohibited actions. It records
fixed task/image selection, explicit grants, exact approvals, model/execution
bounds, zero anonymous execution, no unrestricted repository/shell/network access,
and deferred deployment gates. Existing enforcement is sufficient for this local
scope; no speculative public-mode flag or submission API was added.

Reviewed the archive imports, local proxies, API scopes, fixture configuration and
Docker boundary. All six web test files (13 tests), lint, type checking, production
build and actual HTTP smoke passed. No UI behavior changed, so no new browser
interaction suite was added. Public hosting and production authentication remain
unimplemented by this slice. Stop for human review after local verification.

## Files

Created:

- `docs/adr/0044-local-security-detour.md`
- `docs/security/THREAT_MODEL.md`
- `docs/security/PUBLIC_DEMO.md`
- `docs/operations/PHASE_15.md`

Modified:

- `ROADMAP.md`, `ARCHITECTURE.md`
- `docs/operations/PHASE_12C.md` (pre-existing untracked preflight, preserved)
- `docs/operations/DEVELOPMENT.md`, `SHOWCASE.md`, `TELEMETRY.md`
- `packages/agent_core/src/runveil_core/telemetry.py`
- `apps/worker/src/runveil_worker/telemetry.py`
- `packages/agent_core/tests/test_telemetry.py`
- `packages/persistence/tests/test_execution.py`, `test_telemetry_execution.py`

## Verification environment and results

The checkout's existing Intel Python environment lacked MCP. An attempted
`uv sync --locked --all-packages` failed building cryptography against ARM-only
local compiler tooling. A temporary native Python 3.12 environment then installed
the unchanged lock successfully using:

```sh
UV_PROJECT_ENVIRONMENT=/tmp/runveil-security-venv uv sync --locked --all-packages --python <installed-native-python-3.12>
```

All successful Python commands below use that `UV_PROJECT_ENVIRONMENT`. Node
checks use the installed Node 24.19.0 directory first on PATH. The existing local
PostgreSQL volume rejected the documented example password, so initial integration
setup failed before test execution. No password/data was reset. Its service was
stopped again and acceptance used a dedicated ephemeral PostgreSQL 17.9 container
on loopback port 55432 with public test-only credentials and tmpfs data.

Commands and final results are recorded below; earlier failed environment attempts
are not counted as product regressions or successful verification.

| Command                                                                                                                                                                                                                                                     | Result                                                                                                                                                        |
| ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `uv run ruff format --check .`                                                                                                                                                                                                                              | Passed, 303 files already formatted.                                                                                                                          |
| `uv run ruff check .`                                                                                                                                                                                                                                       | Passed.                                                                                                                                                       |
| `uv run mypy`                                                                                                                                                                                                                                               | Passed, 155 source files.                                                                                                                                     |
| `uv run pytest -m 'not integration' -q`                                                                                                                                                                                                                     | 168 passed.                                                                                                                                                   |
| `uv run pytest -m integration -q --tb=short`                                                                                                                                                                                                                | 216 passed; 11 opt-in Docker cases skipped here, then all passed separately below.                                                                            |
| `uv run alembic upgrade head` and `uv run alembic check`                                                                                                                                                                                                    | Passed against the disposable database; no new upgrade operations.                                                                                            |
| `uv run python scripts/phase5_acceptance.py`                                                                                                                                                                                                                | Passed actual SIGKILL recovery, uncertain-intent failure, active-lease deferral, duplicate acknowledgement and disposable DB removal; offline SQS stubs only. |
| `docker build --network=none -t runveil-sandbox:phase15 sandbox`                                                                                                                                                                                            | Passed using the pinned base image.                                                                                                                           |
| `uv run python scripts/phase10_sandbox_acceptance.py --image <image-id> --output /tmp/runveil-phase15-sandbox.json`                                                                                                                                         | Passed isolation, expected failing baseline, watchdog, output limit and cancellation; cleanup confirmed.                                                      |
| `uv run pytest packages/persistence/tests/test_sandbox_worker.py packages/persistence/tests/test_sandbox_review.py packages/persistence/tests/test_sandbox_patch_worker.py packages/persistence/tests/test_software_worker.py -k real_docker -q --tb=short` | All 11 real Docker cases passed; no remaining skipped Python cases across the combined runs.                                                                  |
| `npm run lint`, `npm run typecheck`, `npm test`, `npm run build`                                                                                                                                                                                            | Passed; 13 tests in six files; production build completed.                                                                                                    |
| `uv run python scripts/smoke.py`                                                                                                                                                                                                                            | Passed API/web health, showcase/operator framing and referrer protections, and configured database readiness.                                                 |
| `npm run format:check`, `git diff --check`, changed-document local link check                                                                                                                                                                               | Passed; 279 relative file links resolved.                                                                                                                     |

Integration/process tests used
`RUNVEIL_TEST_DATABASE_URL=postgresql+psycopg://runveil:runveil-local-only@127.0.0.1:55432/postgres`.
Migrations/smoke used the same disposable server with database `runveil` via
`DATABASE_URL`. Real Docker tests set `RUNVEIL_SANDBOX_IMAGE` to the build's image
ID, also supplied to boundary acceptance:
`sha256:793b47cd3ad42e313cc5596773608d71507b0a56843a95f1730f9c817fb1a8f4`.
These are public local test credentials, not production configuration.

No Terraform source changed, so Terraform validation/mock tests were not rerun.
The separate Phase 12B deployment image/TLS cloud-smoke acceptance was not rerun;
this slice changes local runtime telemetry, not deployment packaging or permissions.
No live AWS, paid provider, production authentication, CI/CD deployment or GPU/vLLM
work ran. The public policy is supported by local tests, not public hosting evidence.

The disposable database container and this slice's sandbox image tag were removed
after verification. No test/acceptance databases or labelled sandbox containers
remained. The existing PostgreSQL volume was preserved and its service left stopped,
as at entry. The native verification environment remains outside the repository at
`/tmp/runveil-security-venv` for reproducing checks. No new generated artifacts were
added to source control.

## Remaining risks

The filtering contract protects metadata handoff, not arbitrary selected source,
durable model/tool payloads or trusted custom tracer code. Docker remains a
controlled-fixture boundary, not hostile multi-tenant isolation. Local bearer auth
has no production user/tenant model; per-run budgets are not aggregate public quotas.
The threat register retains these limitations and the later cloud/public gates.
No phase is closed by this implementation handoff; local 15A–15C await review.

## Resume after review

Resume Phase 12C live AWS acceptance when the owner returns and completes account,
billing and credential setup; then Phase 13 CI/CD, Phase 14 self-hosted inference,
remaining AWS/public-deployment security in Phase 15, and Phase 16 public release.
Provisioning, migrations, health checks, queue/worker acceptance, teardown and
retained-resource cleanup remain pending. Later phases require their review gates.
