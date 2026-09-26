# Runveil

A production-style runtime for reliable, observable and evaluable AI agents.

**Working name · Phase 1C implemented, awaiting review.** This repository contains
immutable agent versions, persisted runs with validated lifecycle transitions,
ordered execution history, checkpoint snapshots, model/tool request and outcome
records, PostgreSQL migrations and
integration tests, plus the Phase 0 API/web foundation.
It does not execute agents. No live demo or benchmark results exist.

[Architecture](ARCHITECTURE.md) · [Roadmap](ROADMAP.md) ·
[Project charter](docs/PROJECT_PLAN.md) · [Verification](docs/operations/PHASE_1C.md)

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
npm run format:check
npm run lint
npm run typecheck
npm test
npm run build
uv run python scripts/smoke.py
```

Integration tests create/migrate/drop only randomly named `runveil_test_*`
databases. They never reset the database named in the admin URL. Without the test
URL they are explicitly skipped; CI sets it and runs the full suite.

The smoke check starts the API and the production web build on temporary local
ports, checks their real HTTP responses, and stops both processes. Run the build
first. It also checks API readiness: 200 with `DATABASE_URL`, 503 without it.
No model keys, paid services or AWS credentials are needed.

## Repository

- `apps/api`: installable Python API package in the uv workspace.
- `apps/web`: Next.js App Router application in the npm workspace.
- `packages/agent_core`: immutable domain snapshots and lifecycle rules.
- `packages/persistence`: PostgreSQL repositories, mappings, migrations and tests.
- `scripts`: process-level smoke verification.
- `docs`: original charter, decisions, naming research and verification record.
- `.github/workflows/ci.yml`: locked installs, formatting, lint, types, tests,
  production build, HTTP smoke checks, migrations and PostgreSQL integration tests.

Workers, execution behavior, benchmarks and Terraform are introduced when their
phases supply actual behavior. See the architecture for the intended boundaries.

## Evidence and limitations

Current verification is recorded in [the Phase 1C handoff](docs/operations/PHASE_1C.md);
[Phase 0 evidence](docs/operations/PHASE_0.md) is retained.
Repository usage and state rules are documented in [persistence operations](docs/operations/PERSISTENCE.md).
Reliability, evaluation, security, inference benchmarks and AWS deployment remain
planned work. Application containers and production delivery are not implemented.
The development servers are not a public deployment configuration.

The previous name had collisions; Runveil still needs public-name clearance.
See [naming research](docs/architecture/NAMING.md).
A final public name and license must be selected before release. No license grant
is implied by this scaffold.
