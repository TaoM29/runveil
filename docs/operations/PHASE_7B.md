# Phase 7B handoff — operational trace console

Implemented and verified 2026-10-01. Review pending. No commit or push.

## Implementation and decisions

Started from a clean checkout. Inspected AGENTS.md, web-specific instructions,
the installed Next.js route/client guides, charter observability/trace goals,
architecture, roadmap, ADRs 0025–0026, Phase 7A evidence, trace API/persistence
contracts and the current approval console/proxy/tests. The next coherent slice
was the local trace UI specified by the roadmap. No project scope conflict arose.

Added `/traces`: manual single-run inspection with a separate read credential,
status, intent counts, persisted durations, known usage/cost and uncertainty,
retry links, approval metadata, final summary, and event/call correlation.
One page of 50 events is retained at a time; continuation binds the event watermark.
Refresh restarts; conflicts/failures/input changes clear the view and late responses
are discarded. Data is escaped text and summaries disclose truncation. Costs use
exact decimal formatting of safe integer nano-USD, not floating-point rounding.

The new GET-only proxy uses the fixed local API origin and caller bearer, validated
pagination, no caching/redirects/cookies, bounded JSON and fixed errors. It adds no
server credential, approval authority or mutation path. The shared extraction is
only the existing bounded stream reader; approval behavior and its tests remain
unchanged. No backend/runtime/persistence/worker, schema, dependency or lockfile
changes were required. [ADR 0027](../adr/0027-local-trace-console.md) records the
UI/proxy decisions; [operations](TRACES.md) provides setup and semantics.

## Files created

- `apps/web/app/traces/page.tsx`: local trace page and metadata.
- `apps/web/app/traces/trace-console.tsx`: bounded inspection UI and credential lifecycle.
- `apps/web/app/api/traces/[runId]/route.ts`: fixed authenticated read-only proxy.
- `apps/web/lib/trace.ts`: typed response validation and exact formatting.
- `apps/web/lib/bounded-body.ts`: existing bounded stream reader extracted for reuse.
- `apps/web/tests/trace-console.test.tsx`: three focused component/contract scenarios.
- `apps/web/tests/trace-proxy.test.ts`: two proxy boundary scenarios.
- `docs/adr/0027-local-trace-console.md`.
- `docs/operations/PHASE_7B.md`: this handoff.
- `docs/operations/evidence/phase7/trace-approval.png`: actual browser view, public fixture.
- `docs/operations/evidence/phase7/browser-acceptance.json`: sanitized persisted evidence.

## Files modified

- `apps/web/app/page.tsx`: full-document link to trace inspection.
- `apps/web/app/api/approvals/[runId]/route.ts`: imports unchanged bounded reader.
- `scripts/smoke.py`: checks both production console pages and security headers.
- `README.md`, `ARCHITECTURE.md`, `ROADMAP.md`, `docs/operations/DEVELOPMENT.md`,
  `docs/operations/TRACES.md`: current scope, setup, semantics and next slice.

## Verification

Python 3.12.14, uv 0.12.19, Node 24.19.0, actual production Next.js build and Codex
in-app browser. All services bound to loopback. Verification used a newly created
Compose project `runveil-phase7b-checks` on port 54329, explicit user/database
`runveil` and the documented local-only password. Integration and process-death
acceptance commands used their own isolated temporary databases. Browser fixtures
used this task's disposable Compose database; no existing database was reset.

Environment for the commands below:

```sh
export PATH=/Users/taom/.nvm/versions/node/v24.19.0/bin:$PATH
export POSTGRES_USER=runveil POSTGRES_DB=runveil
export POSTGRES_PASSWORD=runveil-local-only POSTGRES_PORT=54329
export DATABASE_URL='postgresql+psycopg://runveil:runveil-local-only@127.0.0.1:54329/runveil'
export RUNVEIL_TEST_DATABASE_URL='postgresql+psycopg://runveil:runveil-local-only@127.0.0.1:54329/postgres'
```

- `docker compose -p runveil-phase7b-checks up -d --wait --wait-timeout 90` — passed.
- `uv run alembic upgrade head`; `uv run alembic check` — passed; no new operations.
- `uv run ruff format --check .`; `uv run ruff check .`; `uv run mypy` — passed;
  mypy checked 99 Python source files.
- `uv run pytest --tb=short` — **289 passed**, including 153 PostgreSQL cases,
  no skips, in 89.67 seconds. No new backend tests were needed.
- `uv run python scripts/phase5_acceptance.py` — passed process-death recovery,
  uncertain-intent failure, lease deferral, and duplicate acknowledgement.
- `npm run lint`; `npm run typecheck`; `npm test`; `npm run build` — passed;
  **11 web tests**, including five new focused scenarios. Existing approval tests pass.
- `uv run python scripts/smoke.py`; `env -u DATABASE_URL uv run python scripts/smoke.py`
  — passed real API/web HTTP, approval/trace production pages, framing/referrer headers,
  and both readiness states.
- `npm run format:check`; `git diff --check` — passed.

Early typing caught BigInt literal syntax incompatible with the existing TypeScript
target and a test-header union inferred with optional undefined properties. Exact
string-based decimal formatting and an explicit header-map type resolved both,
without changing compiler targets or dependencies. Subsequent typing/tests/build
passed. No unresolved failure, live provider/AWS call, or paid service was involved.

### Real browser verification

Actual production web on port 58102 forwarded to actual API on 58101, with a fresh
random trace credential supplied only through a private temporary file into tool
memory and then the browser's password field. The API had approval authentication
disabled. No mocked browser responses or authentication bypasses were used.

- Completed `fixture-calls-v1` run: 17 events, two model intents, one tool intent,
  20 input/10 output tokens, USD 0.000050000 estimate, final fixture summary.
- Paused `repository-patch-v1` run: 22 events, PENDING approval, no mutation intent,
  released worker lease and unchanged public fixture file after browser inspection.
- A real offline scripted/core run with 14 model calls and 13 fixture tools:
  113 events, visited as 1–50, 51–100 and 101–113. Older schema accounting displayed
  unavailable rather than invented zeros. The last page identified the snapshot end.
- Wrong token refused without evidence; correcting it restored inspection.
  Forget and reload cleared fields/evidence. Navigation to approvals used blank
  separate fields; browser Back also returned to blank trace fields.
- An actual HTTP POST to the trace proxy returned 405. Persisted snapshots matched
  the displayed totals. Server logs contained no credential.

The [sanitized evidence](evidence/phase7/browser-acceptance.json) preserves run IDs,
accounting and approval snapshots. The [browser screenshot](evidence/phase7/trace-approval.png)
shows descriptive approval metadata and accounting. Temporary coordinators were
not added as a second test framework. Browser, services, generated credential,
checkout and task-owned Compose volume were removed after verification
(`docker compose -p runveil-phase7b-checks down --volumes`).

Component tests cover changed-watermark rejection, late responses after edits,
Forget/pagehide, escaped content, unknown/subtotal semantics, invalid/foreign/unsafe
responses, and bounded pagination. Proxy tests cover local destination/auth/header
boundaries, invalid queries, HTML/oversized/stalled responses and safe errors.
These supplement browser observations rather than claiming exhaustive browser
fault-injection or cross-browser certification.

## Remaining boundaries and next slice

One trusted local operator, no run discovery, public deployment, per-run ACLs,
dashboard, auto-refresh or execution controls. Safe JavaScript integer validation
can refuse unusually large administrator-created accounting rather than displaying
rounded values. Active runs may invalidate a page and require refresh. Memory-only
credentials do not defend against extensions, password managers or hostile
same-origin scripts. Approval metadata does not establish current action authority.

OpenTelemetry, safe structured logs/correlation, per-attempt usage/latency projection
and full Phase 7 acceptance remain open. Next: a focused telemetry instrumentation
slice around existing execution boundaries, keeping the durable trace authoritative
and telemetry failures outside execution/authorization decisions. Stop for review.
