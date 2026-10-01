# Local development and verification

Run all commands from the repository root. These instructions configure local
development services, not a public deployment.

## Local quickstart

Prerequisites: Git, uv **0.12.19**, Node.js **24.19.0** (see `.nvmrc`), npm, and Docker
with Compose v2. Python 3.12 is selected by `.python-version`; uv can install it.
Use `nvm install && nvm use` if you use nvm. Install uv using the
[official instructions](https://docs.astral.sh/uv/getting-started/installation/).

From the repository root:

```sh
export POSTGRES_PASSWORD=runveil-local-only
uv sync --locked --all-packages
npm ci
docker compose config --quiet
docker compose up -d --wait --wait-timeout 90
docker compose exec -T postgres psql -U runveil -d runveil -v ON_ERROR_STOP=1 -c 'SELECT 1;'
export DATABASE_URL='postgresql+psycopg://runveil:runveil-local-only@127.0.0.1:5432/runveil'
uv run alembic upgrade head
uv run alembic check
```

The URL above matches the local-only password exported for Compose. Adjust it
for your own credentials/port and URL-encode special characters. No `.env` file
is required. Compose can read one if you already use it; Python and Alembic use
exported environment variables and do not auto-load `.env`.

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
Export `POSTGRES_PORT` if that port is occupied and update the database URLs to
match. Keep `POSTGRES_PASSWORD` set for subsequent Compose commands; an unset or
empty password is rejected. Changing it does not change an existing database's
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
[provider operations](MODELS.md#opt-in-live-verification).

## Runtime operations

- [In-process demonstration](RUNTIME.md)
- [Durable worker and execution profiles](WORKER.md)
- [Repository read/search tools](REPOSITORY_TOOLS.md)
- [Model providers](MODELS.md)
- [Persistence and migrations](PERSISTENCE.md)
- [SQS notification adapter](BROKER.md)
- [Quarantine inspection and release](ADMISSION.md)
- [Local durable patch review](APPROVALS.md)
- [Controlled approved file replacement](PATCHES.md)
- [Authenticated local approval API](APPROVAL_API.md)
- [Local operator console](APPROVAL_CONSOLE.md)
- [Phase 5 acceptance evidence](PHASE_5.md)
- [Phase 6 browser acceptance and closure](PHASE_6.md)
- [Authenticated read-only run traces and browser console](TRACES.md)
- [Opt-in execution telemetry and JSON output](TELEMETRY.md)
- [Phase 7 integrated acceptance and closure](PHASE_7.md)

- [Offline deterministic evaluation calibration](EVALUATIONS.md)
