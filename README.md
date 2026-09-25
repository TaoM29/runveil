# AgentRail

A production-style runtime for reliable, observable and evaluable AI agents.

**Working name · Phase 0 foundation only.** This repository currently contains a
FastAPI health endpoint, a minimal Next.js console, local PostgreSQL and quality
checks. It does not yet execute agents. No live demo or benchmark results exist.

[Architecture](ARCHITECTURE.md) · [Roadmap](ROADMAP.md) ·
[Project charter](docs/PROJECT_PLAN.md) · [Verification](docs/operations/PHASE_0.md)

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
docker compose exec -T postgres psql -U agentrail -d agentrail -v ON_ERROR_STOP=1 -c 'SELECT 1;'
```

Run these in separate terminals:

```sh
uv run uvicorn agentrail_api.main:app --reload --host 127.0.0.1 --port 8000
```

```sh
npm run dev:web
```

Open [the console](http://localhost:3000), [web health](http://localhost:3000/health),
[API health](http://localhost:8000/health) or [API docs](http://localhost:8000/docs).
Health endpoints are **liveness only**; they do not assert database readiness.
The API does not connect to PostgreSQL until Phase 1.

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
uv run pytest
npm run format:check
npm run lint
npm run typecheck
npm test
npm run build
uv run python scripts/smoke.py
```

The smoke check starts the API and the production web build on temporary local
ports, checks their real HTTP responses, and stops both processes. Run the build
first. No model keys, paid services or AWS credentials are needed.

## Repository

- `apps/api`: installable Python API package in the uv workspace.
- `apps/web`: Next.js App Router application in the npm workspace.
- `scripts`: process-level smoke verification.
- `docs`: original charter, decisions, naming research and verification record.
- `.github/workflows/ci.yml`: locked installs, formatting, lint, types, tests,
  production build, HTTP smoke checks and PostgreSQL startup.

Runtime packages, workers, benchmarks and Terraform are introduced when their
phases supply actual behavior. See the architecture for the intended boundaries.

## Evidence and limitations

Phase 0 verification is recorded in [the handoff](docs/operations/PHASE_0.md).
Reliability, evaluation, security, inference benchmarks and AWS deployment remain
planned work. Application containers and production delivery are not implemented.
The development servers are not a public deployment configuration.

The working name has existing collisions; see [naming research](docs/architecture/NAMING.md).
A final public name and license must be selected before release. No license grant
is implied by this scaffold.
