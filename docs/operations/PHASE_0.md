# Phase 0 handoff

Date: 2026-09-25. Foundation only. No agent behavior, commit or push.

## Implementation summary

The repository already had Git initialized on `main`, with no commits, remote,
tracked files or project instructions. Added uv/Python and npm/Next.js workspaces,
FastAPI and web liveness endpoints, strict quality tooling, deterministic tests,
production HTTP smoke checks, PostgreSQL Compose and a GitHub Actions workflow.
The supplied charter is preserved byte-for-byte in `docs/PROJECT_PLAN.md`.

## Architectural decisions

- Custom Python runtime, single-agent-first; see ADR 0001.
- PostgreSQL system of record; SQLAlchemy, Alembic and schema work begin in Phase 1.
- One lockfile per ecosystem; only create packages when they contain real behavior.
- Health endpoints report process liveness, independent of database readiness.
- Docker supplies local PostgreSQL; AWS and Terraform remain deployment targets.
- Runveil is a working name with known collisions; see naming research.

## Verification

Executed on macOS with Python 3.12.14, uv 0.12.19, Node 24.19.0,
Docker Engine 28.5.2 and Compose 2.40.3. Node and uv installation directories
were added to PATH for verification. Commands run from the repository root:

| Command                                                                                        | Result                                                                |
| ---------------------------------------------------------------------------------------------- | --------------------------------------------------------------------- |
| `uv sync --locked --all-packages`                                                              | Passed; lock matches manifests                                        |
| `npm ci`                                                                                       | Passed; clean locked install                                          |
| `uv run ruff format --check .`                                                                 | Passed                                                                |
| `uv run ruff check .`                                                                          | Passed                                                                |
| `uv run mypy`                                                                                  | Passed; five project Python files                                     |
| `uv run pytest`                                                                                | Passed; two API tests                                                 |
| `npm run format:check`                                                                         | Passed                                                                |
| `npm run lint`                                                                                 | Passed; zero warnings                                                 |
| `npm run typecheck`                                                                            | Passed; generated route types and strict TypeScript                   |
| `npm test`                                                                                     | Passed; one web health contract test                                  |
| `npm run build`                                                                                | Passed; production Next.js build                                      |
| `uv run python scripts/smoke.py`                                                               | Passed; real API health, web health and rendered production home page |
| `docker compose config --quiet`                                                                | Passed with local `.env`                                              |
| `docker compose up -d --wait --wait-timeout 90`                                                | Passed; PostgreSQL healthy                                            |
| `docker compose exec -T postgres psql -U runveil -d runveil -v ON_ERROR_STOP=1 -c 'SELECT 1;'` | Passed; returned 1                                                    |
| `docker compose ps`                                                                            | Healthy; loopback port binding confirmed                              |
| `docker compose down`                                                                          | Passed; database volume preserved                                     |
| `uv run uvicorn runveil_api.main:app --reload --host 127.0.0.1 --port 8000`                    | Development server booted                                             |
| `npm run dev:web`                                                                              | Development server booted                                             |
| `curl --fail --silent http://127.0.0.1:8000/health`                                            | HTTP 200; expected API JSON                                           |
| `curl --fail --silent http://127.0.0.1:3000/health`                                            | HTTP 200; expected web JSON                                           |
| `npm audit`                                                                                    | Zero reported vulnerabilities                                         |
| Byte comparison of `docs/PROJECT_PLAN.md` with the supplied charter                            | Identical to supplied charter                                         |

Both development servers and the database container were stopped after checks.
The production smoke script cleans up its own processes. Initial formatting and
typing failures were fixed before the passing checks above.

## Remaining concerns

- Hosted GitHub Actions has **not executed**: there is no remote and pushing was
  prohibited. Its application/database commands passed locally; hosted action
  setup and Linux runner behavior remain unverified until a real run after review.
- ESLint 9.39.5 emits an upstream support/deprecation warning. ESLint 10.11.0 was
  tested but crashes in the Next.js React lint plugin with
  `contextOrFilename.getFilename is not a function`. Keep the compatible major
  until that integration supports an upgrade. The dependency audit is clean.
- uv reported a macOS Python dynamic-library install-name warning during install.
  Current checks pass; native extension builds may need investigation later.
- The host's Intel Python invoking Apple Git hit an `xcrun` architecture mismatch
  during handoff generation. Shell Git commands work; no repository change was
  needed. This did not affect application verification.
- Public name and open-source license remain undecided.
- No persistence, migrations, runtime, worker, authentication, deployment or
  evaluation functionality exists yet. Health checks prove liveness only.

## Recommended next slice

After independent review, begin Phase 1 with immutable agent definitions/versions,
validated run transitions, PostgreSQL persistence and an initial Alembic migration,
backed by database integration tests. Do not advance before review.

## Files modified

None: there were no pre-existing project files.

## Files created

All repository additions are listed below. Next.js generated `apps/web/AGENTS.md`
and `apps/web/CLAUDE.md` during development startup. Ignored local artifacts include
`.env`, `.venv`, dependencies, build output and caches. The local PostgreSQL named
volume is retained; the test container and network have been removed.

- `.editorconfig`
- `.env.example`
- `.github/workflows/ci.yml`
- `.gitignore`
- `.nvmrc`
- `.prettierignore`
- `.python-version`
- `ARCHITECTURE.md`
- `CONTRIBUTING.md`
- `README.md`
- `ROADMAP.md`
- `apps/api/pyproject.toml`
- `apps/api/src/runveil_api/__init__.py`
- `apps/api/src/runveil_api/health.py`
- `apps/api/src/runveil_api/main.py`
- `apps/api/tests/test_health.py`
- `apps/web/AGENTS.md`
- `apps/web/CLAUDE.md`
- `apps/web/app/globals.css`
- `apps/web/app/health/route.ts`
- `apps/web/app/layout.tsx`
- `apps/web/app/page.tsx`
- `apps/web/eslint.config.mjs`
- `apps/web/next-env.d.ts`
- `apps/web/package.json`
- `apps/web/postcss.config.mjs`
- `apps/web/tests/health.test.ts`
- `apps/web/tsconfig.json`
- `docker-compose.yml`
- `docs/PROJECT_PLAN.md`
- `docs/adr/0001-custom-runtime.md`
- `docs/adr/0002-foundation-boundaries.md`
- `docs/architecture/NAMING.md`
- `docs/operations/PHASE_0.md`
- `package-lock.json`
- `package.json`
- `pyproject.toml`
- `scripts/smoke.py`
- `uv.lock`
