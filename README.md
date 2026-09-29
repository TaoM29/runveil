# Runveil

A production-style runtime for reliable, observable and evaluable AI agents.

**Working name · Phase 5 acceptance complete; ready for closure review. Phase 2 hosted acceptance complete.** This repository contains
immutable agent versions, persisted runs with validated lifecycle transitions,
ordered execution history, checkpoint snapshots, model/tool request and outcome
records, PostgreSQL migrations and integration tests, plus normalized model
contracts, structured action validation, scripted and OpenAI-compatible HTTP
providers, and the Phase 0 API/web foundation. The opt-in hosted acceptance check
[passed](docs/operations/PHASE_2B.md#subsequent-hosted-live-acceptance--complete),
based on user-reported evidence.
A bounded in-process runtime executes persisted model/tool loops with explicit
grants and bounded native repository read/search tools. File access requires an
operator-selected root and exact allowlist. A durable worker supports leased ownership and conservative checkpoint recovery,
plus opt-in bounded model retries, elapsed/token/cost budgets and repeated-tool
limits plus separate model/tool call limits and a pinned read-only repository profile.
An opt-in SQS notification adapter uses a transactional outbox and PostgreSQL claims
for the public fixture profile; verification is offline, with no live AWS acceptance.
Repeated configuration rejections in that profile enter durable quarantine with verified operator release.
No public live demo or benchmark results exist.

[Architecture](ARCHITECTURE.md) · [Roadmap](ROADMAP.md) ·
[Project charter](docs/PROJECT_PLAN.md) · [Verification](docs/operations/PHASE_5K.md)

## Purpose

Build the engineering infrastructure around a model: durable execution, typed
tools, approvals, traces and reproducible evaluation. The eventual application
will solve controlled repository tasks in isolated environments and require human
approval of the resulting patch. Evidence takes priority over feature count.

## Local quickstart

Prerequisites: Git, uv **0.12.19**, Node.js **24.19.0** (see `.nvmrc`), npm, and Docker
with Compose v2. Python 3.12 is selected by `.python-version`; uv can install it.
Use `nvm install && nvm use` if you use nvm. Install uv using the
[official instructions](https://docs.astral.sh/uv/getting-started/installation/).

From the repository root:

```sh
cp .env.example .env
uv sync --locked --all-packages
npm ci
docker compose config --quiet
docker compose up -d --wait --wait-timeout 90
docker compose exec -T postgres psql -U runveil -d runveil -v ON_ERROR_STOP=1 -c 'SELECT 1;'
export DATABASE_URL='postgresql+psycopg://runveil:runveil-local-only@127.0.0.1:5432/runveil'
uv run alembic upgrade head
uv run alembic check
```

The URL above matches the example local credentials. Adjust it for your own
credentials/port and URL-encode special characters. Compose reads `.env`; Python
and Alembic use exported environment variables and do not auto-load `.env`.
Existing checkouts should merge the new example variables into their local `.env`.

Run these in separate terminals (export `DATABASE_URL` in the API terminal):

```sh
uv run uvicorn runveil_api.main:app --reload --host 127.0.0.1 --port 8000
```

```sh
npm run dev:web
```

Open [the console](http://localhost:3000), [web health](http://localhost:3000/health),
[API health](http://localhost:8000/health) or [API docs](http://localhost:8000/docs).
`/health` endpoints report **liveness only**. The API also exposes
[`/ready`](http://localhost:8000/ready): HTTP 200 when a bounded database query
succeeds, otherwise a generic 503, including when `DATABASE_URL` is unset.
Readiness checks connectivity, not migration state; migrations are explicit and
never run at application startup.

PostgreSQL binds to loopback only, defaults to port 5432, and uses a named volume.
Set `POSTGRES_PORT` in `.env` if that port is occupied. The example password is
local-only. Changing credentials in `.env` does not change an existing database's
credentials. `docker compose down` stops the service and preserves data.
`docker compose down --volumes` **deletes local database data**; use it only for an
intentional reset.

## Quality checks

```sh
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest -m 'not integration'
# PostgreSQL must be running; this role needs CREATEDB for isolated test databases.
export RUNVEIL_TEST_DATABASE_URL='postgresql+psycopg://runveil:runveil-local-only@127.0.0.1:5432/postgres'
uv run pytest -m integration
uv run python scripts/phase5_acceptance.py
npm run format:check
npm run lint
npm run typecheck
npm test
npm run build
uv run python scripts/smoke.py
```

Integration tests create/migrate/drop only randomly named `runveil_test_*`
databases. The POSIX process-death acceptance command similarly owns one temporary
`runveil_acceptance_*` database and uses offline SDK stubs. Neither resets the
database named in the admin URL. Integration tests skip when the test URL is unset;
the acceptance command requires it and fails explicitly if missing. CI sets it
and runs both.

The smoke check starts the API and the production web build on temporary local
ports, checks their real HTTP responses, and stops both processes. Run the build
first. It also checks API readiness: 200 with `DATABASE_URL`, 503 without it.
No model keys, paid services or AWS credentials are needed for these checks.
For the separate, explicitly opt-in hosted check, see
[provider operations](docs/operations/MODELS.md#opt-in-live-verification).

## Repository

- `apps/worker`: PostgreSQL polling worker plus an opt-in SQS notification adapter; fixed fixture and repository profiles.
- `apps/api`: installable Python API package in the uv workspace.
- `apps/web`: Next.js App Router application in the npm workspace.
- `packages/agent_core`: domain snapshots, model contracts, scripted provider and bounded execution loop.
- `packages/model_providers`: bounded HTTP adapter and opt-in live fixture command.
- `packages/tool_runtime`: bounded repository read/search adapters with explicit file disclosure.
- `packages/persistence`: PostgreSQL repositories, mappings, migrations and tests.
- `scripts`: process-level smoke verification.
- `docs`: original charter, decisions, naming research and verification record.
- `.github/workflows/ci.yml`: locked installs, formatting, lint, types, tests,
  production build, HTTP smoke checks, migrations and PostgreSQL integration tests.

Broader worker profiles, mutation tools, benchmarks and Terraform are introduced when their
phases supply actual behavior. See the architecture for the intended boundaries.

## Evidence and limitations

The [Phase 5 acceptance audit](docs/operations/PHASE_5.md) maps the charter criteria
to evidence, including actual worker-process death, recovery and duplicate delivery.
Production/live AWS acceptance and hosted retry safety are not claimed.
Current verification is recorded in [the Phase 5K handoff](docs/operations/PHASE_5K.md);
[Phase 0 evidence](docs/operations/PHASE_0.md) is retained.
Run the offline persisted demonstration with `uv run python scripts/runtime_demo.py`
after migration and database configuration. It creates and retains one new run; see
[runtime operations](docs/operations/RUNTIME.md).
Run the durable offline worker with `uv run python -m runveil_worker submit`, then
`uv run python -m runveil_worker work --once`. Add `--profile fixture-retry-v1`
to both commands for the durable retry demonstration, or `--profile fixture-budget-v1`
for the same workflow with a 30-second elapsed budget. Use `fixture-token-v1`
for elapsed plus reported-token limits and synthetic usage, or `fixture-cost-v1`
for pinned synthetic pricing and cost limits. `fixture-loop-v1` demonstrates
rejection of a third identical tool call. `fixture-calls-v1` succeeds exactly at
its two-model/one-tool limits; see [worker operations](docs/operations/WORKER.md).
`repository-read-v1` captures an explicit file allowlist and refuses recovery if its
workspace or tool implementation changes; see [worker setup](docs/operations/WORKER.md#pinned-repository-recovery).
For quarantine inspection/release, see [admission operations](docs/operations/ADMISSION.md).
For the optional SQS submission/relay/consumer path, see [broker operations](docs/operations/BROKER.md).
Repository tool setup and limits are documented in [repository tools](docs/operations/REPOSITORY_TOOLS.md).
Model contract usage is documented in [model operations](docs/operations/MODELS.md).
Repository usage and state rules are documented in [persistence operations](docs/operations/PERSISTENCE.md).
Reliability, evaluation, security, inference benchmarks and AWS deployment remain
planned work. Application containers and production delivery are not implemented.
The development servers are not a public deployment configuration.

The previous name had collisions; Runveil still needs public-name clearance.
See [naming research](docs/architecture/NAMING.md).
A final public name and license must be selected before release. No license grant
is implied by this scaffold.
