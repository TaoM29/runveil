# Phase 7A handoff — durable run trace API

Implemented 2026-10-01. Review pending; no commit or push.

## Scope and decisions

Started from a clean checkout. Inspected the charter, roadmap, architecture,
accepted history/accounting/approval ADRs, Phase 6 closure evidence and the existing
API, persistence, runtime and controlled mutation implementation. The explicit
Phase 7 request supersedes the roadmap's prior requirement for separate
continuation authorization. Phase 6 is complete within its documented scope.

The smallest selected slice is a read-only durable trace API, establishing evidence
for the later trace UI and telemetry work. It exposes ordered events, model/tool
identities and outcomes, request-to-outcome durations, retry links, checkpoint
usage/cost/error/final-summary evidence, and approval metadata. A separate trace
credential carries no approval authority. Consistent read-only database snapshots
avoid worker locks; continuation binds the event watermark and refuses changes.
Content-bearing request/result/event JSON is excluded from the projection.

[ADR 0026](../adr/0026-durable-run-trace.md) records the consistency, security and
measurement decisions. [Operations](TRACES.md) documents setup, every field's
meaning, pagination, errors and limitations. Existing execution, schema, worker
claims, mutation authorization and uncertain-outcome behavior are unchanged.
No dependency or lockfile changes, new packages, generic instrumentation framework
or speculative abstractions were needed. The original charter remains accurate.

## Files created

- `apps/api/src/runveil_api/traces.py`: bounded authenticated GET route.
- `packages/persistence/src/runveil_persistence/traces.py`: typed content-minimized projections.
- `apps/api/tests/test_trace_http.py`: capability separation and HTTP input bounds.
- `packages/persistence/tests/test_traces.py`: four focused database scenarios.
- `docs/adr/0026-durable-run-trace.md`.
- `docs/operations/TRACES.md`.
- `docs/operations/PHASE_7A.md`: this handoff.

## Files modified

- `apps/api/src/runveil_api/main.py`: trace credential lifecycle and router registration.
- `packages/persistence/tests/test_cost_budget.py`: reuse existing failure/partial-usage
  cases to compare trace accounting directly with durable runtime accounting.
- `ARCHITECTURE.md`, `ROADMAP.md`, `README.md`, `docs/operations/DEVELOPMENT.md`:
  current scope, Phase 6 continuation and trace links.

## Verification

Environment: Python 3.12.14, uv 0.12.19, Node 24.19.0. Compose project
`runveil-phase7-checks`, loopback port 54329, explicit user/database `runveil`,
documented development-only password. The test/acceptance commands create and
remove their own isolated databases; no existing application database was reset.
The disposable Compose service/volume were created for this task only and removed
after verification with `docker compose -p runveil-phase7-checks down --volumes`.

Commands use these nonsecret local fixture settings:

```sh
export PATH=/Users/taom/.nvm/versions/node/v24.19.0/bin:$PATH
export POSTGRES_USER=runveil POSTGRES_DB=runveil
export POSTGRES_PASSWORD=runveil-local-only POSTGRES_PORT=54329
export DATABASE_URL='postgresql+psycopg://runveil:runveil-local-only@127.0.0.1:54329/runveil'
export RUNVEIL_TEST_DATABASE_URL='postgresql+psycopg://runveil:runveil-local-only@127.0.0.1:54329/postgres'
```

Checks:

- `docker compose -p runveil-phase7-checks config --quiet`;
  `docker compose -p runveil-phase7-checks up -d --wait --wait-timeout 90`;
  `docker compose -p runveil-phase7-checks exec -T postgres psql -U runveil -d runveil -v ON_ERROR_STOP=1 -c 'SELECT 1;'`
  — passed.
- `uv run alembic upgrade head`; `uv run alembic check` — passed, no new upgrade operations.
- `uv run ruff format --check .`; `uv run ruff check .`; `uv run mypy` — passed;
  99 Python source files checked by mypy.
- `uv run pytest --tb=short` — **289 passed**, including 153 PostgreSQL integration
  cases, no skips. The corrected full rerun passed in 85.75 seconds.
- `uv run python scripts/phase5_acceptance.py` — passed actual process-death recovery,
  uncertain-intent failure without replay, lease deferral and duplicate acknowledgement.
- `npm run lint`; `npm run typecheck`; `npm test`; `npm run build` — passed;
  six web tests and production build.
- `uv run python scripts/smoke.py`; `env -u DATABASE_URL uv run python scripts/smoke.py`
  — passed real API/web health, production page/security headers and both readiness states.
- `npm run format:check`; `git diff --check` — passed.

Five new tests cover capability separation/input bounds, paginated history and
retry/accounting agreement, nonblocking snapshot consistency across a concurrent
commit, read-only approval inspection/content exclusion, and unresolved intent,
legacy accounting and summary truncation. Existing partial-usage/cost tests gain
projection assertions without adding cases. No browser acceptance is needed for
this backend-only slice; no live provider/AWS calls or dependency installs ran.
Manifests and lockfiles were unchanged.

During development, inherited Compose identity settings caused the first database
setup to create the wrong role. Only this task's new disposable volume was recreated
with explicit settings. A retry test initially reused a clock advanced by one day,
correctly triggering the elapsed deadline; it now anchors the clock to this run's
actual start. A missing test invocation ID was caught by typing and corrected. The first full
run had already collected the old fixture (288 passed, one failed); the corrected
focused tests and subsequent complete run passed.
These were setup/test issues, not production boundary changes.

## Remaining concerns and recommended next slice

This is a local shared read capability, not per-run ACLs or a public trace API.
Final summaries and labels remain untrusted operator data, not automatically
redacted output. Active history can invalidate pagination. Durations are persisted
wall time, not provider timing. Historical accounting remains unavailable when
never recorded, and unknown usage remains explicit. Per-attempt usage/latency,
price-detail projection, OpenTelemetry, structured logs and browser traces remain
open; full Phase 7 acceptance is not claimed.

After review, add the focused trace UI over this read-only API. Keep telemetry
instrumentation/export a separate slice, preserving persisted history as authority.
Stop for review here.
