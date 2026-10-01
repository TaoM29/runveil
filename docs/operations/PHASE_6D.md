# Phase 6D handoff — local operator approval API

## Review status and scope

Implemented on 2026-10-01; stop for review. No commit or push was made.
The working tree was clean at the start. Inspected the charter, architecture,
roadmap, ADRs 0021–0023, completed Phase 6C implementation/handoff, repository
instructions and development/CI checks before implementation.

The next planned work was an authenticated API and small UI. This slice completes
the HTTP authority boundary first, keeping the review focused. The console remains
unchanged; Phase 6 HTTP/UI acceptance is not closed. No runtime, writer, repository
resolver or database migration was changed.

## Implementation and decisions

- `GET /approvals/{run_id}` exposes the exact proposal, immutable digest and
  approval identity, profile, run status/revision, workspace fingerprints and
  mutation status/error under the existing run-row lock.
- `POST /approvals/{run_id}/decision` requires the inspected profile, approval ID,
  revision and digest. It invokes the appropriate existing transactional resolver
  and acknowledges only after commit. Duplicate/concurrent or stale decisions
  fail without a second outcome.
- A generated local operator bearer capability enables both routes. Missing or
  malformed startup configuration disables them. Authentication precedes request
  parsing/database access, uses digest comparison and never enters durable history.
- Strict JSON input rejects extra fields and is bounded to 2 KiB; a five-second
  cooperative deadline covers streaming input and database work. Fixed error codes
  do not reflect sensitive input. Responses are non-cacheable. OpenAPI describes
  bearer authentication, the decision body and inspection response.
- HTTP decisions do not dispatch workers or grant WRITE. Profile separation,
  original deadlines, workspace identity and mutation intent/recovery boundaries
  remain those of ADRs 0021–0023. API direct core/SQLAlchemy dependencies are now
  explicit, with a matching lockfile and no new resolved package versions.

See [ADR 0024](../adr/0024-local-operator-approval-api.md) for security scope and
[operations](APPROVAL_API.md) for setup, requests, consequences and failure handling.

## Files created and modified

Created:

- `apps/api/src/runveil_api/approvals.py`
- `apps/api/tests/test_approval_http.py`
- `packages/persistence/tests/test_approval_api.py`
- `docs/adr/0024-local-operator-approval-api.md`
- `docs/operations/APPROVAL_API.md`
- `docs/operations/PHASE_6D.md`

Modified:

- `apps/api/src/runveil_api/main.py`
- `apps/api/pyproject.toml`, `uv.lock`
- `README.md`, `ARCHITECTURE.md`, `ROADMAP.md`
- `docs/operations/DEVELOPMENT.md`, `APPROVALS.md`, `PATCHES.md`

## Verification

Local Python 3.12.14/uv 0.12.19 and Node 24.19.0. PostgreSQL used isolated Compose
project `runveil-phase6-checks`, explicit `POSTGRES_USER=runveil`, `POSTGRES_DB=runveil`,
port 54329 and the documented local-only development password. Test databases were
randomly created/migrated/dropped by the existing fixtures. No hosted provider,
live AWS or paid service was used.

Commands and results:

- `uv lock`; `uv sync --locked --all-packages` — passed. An initial incorrect
  workspace distribution name was corrected before generating the final lockfile.
- `npm ci` — passed, zero reported vulnerabilities. Existing install-policy warnings
  for fsevents/unrs-resolver scripts and an ESLint deprecation notice remain;
  no install-script authorization or dependency upgrade was made.
- `uv run ruff format --check .`; `uv run ruff check .` — passed.
- `uv run mypy` — passed, 95 source files.
- `uv run pytest -m 'not integration'` — **135 passed**.
- `DATABASE_URL=… uv run alembic upgrade head`; `DATABASE_URL=… uv run alembic check`
  — passed; no new upgrade operations detected.
- `RUNVEIL_TEST_DATABASE_URL=… uv run pytest -m integration` — **149 passed**.
- `RUNVEIL_TEST_DATABASE_URL=… uv run python scripts/phase5_acceptance.py` — passed:
  actual SIGKILL checkpoint continuation, uncertain-intent failure without replay,
  active-lease deferral, duplicate acknowledgement and disposable database cleanup.
- `npm run format:check`; `npm run lint`; `npm run typecheck`; `npm test`;
  `npm run build` — passed; the existing single web test passed.
- `DATABASE_URL=… uv run python scripts/smoke.py` and
  `env -u DATABASE_URL uv run python scripts/smoke.py` — passed real API/web HTTP
  liveness, production page and both readiness states.
- A temporary inline `uv run python` process check started the real Uvicorn server
  with a generated in-memory secret: unauthorized GET returned 401, authenticated
  missing approval returned 404, malformed decision returned 422/no-store, OpenAPI
  included security/body contracts, and server logs did not contain the token.
- `git diff --check` — passed.

Eight focused new cases cover fail-closed startup/auth/input, all three profiles
with approval and rejection, stale identity/profile/revision/digest, concurrent
one-time decisions, unchanged history after refusals, preserved lease/deadline,
no HTTP write, separate worker WRITE denial followed by explicit authorized apply,
post-apply inspection, and cancellation after resolver writes rolling back.
Initial formatting/type/test naming issues were fixed. An initial test incorrectly
expected denied worker execution to return a failure result; it was corrected to
assert the existing `tool_permission_denied` exception and unchanged file.
Final focused checks passed after corrections; no unresolved check failures.

## Limits and next slice

This is a local single-operator capability, not named reviewer authentication,
per-run ACLs, tenant isolation, TLS termination or a public deployment. Every token
holder can inspect/decide supported approvals in this installation. Format checks
do not establish entropy; operators must generate the secret. Do not log headers
or proposal content. No browser acceptance is claimed.

A response lost during commit has an uncertain client outcome. Inspect again;
never infer rollback or automatically repeat a decision. Mutation failure can
still mean file contents changed, as in Phase 6C; inspection exposes durable
mutation evidence, not a live filesystem reconciliation.

Recommended next slice: the small operator UI using this API, with ephemeral
credential handling, exact before/after inspection, explicit profile consequences,
revision-bound decisions and refresh after uncertain/stale outcomes. Then verify
the complete pause/inspect/approve-or-reject/controlled-worker flow through the UI.
Stop for review before continuing.
