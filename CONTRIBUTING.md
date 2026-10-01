# Contributing

Follow [AGENTS.md](AGENTS.md) for project scope, evidence, security and handoff
rules. Use the [development guide](docs/operations/DEVELOPMENT.md)
for setup and validation, including PostgreSQL integration and process-death
acceptance. The [workflow](.github/workflows/ci.yml) runs these checks in CI.

Use `uv sync --locked --all-packages` and `npm ci` for normal setup. When changing
dependencies, update the manifest and lockfile together (`uv lock` or `npm install`)
and verify locked installs again. Format with `uv run ruff format .` and
`npm run format`. The original charter is preserved verbatim and excluded from
Prettier. Run commands from the repository root.

Tests must be deterministic and offline once dependencies are installed. Live
provider checks are separate and opt-in; see [model operations](docs/operations/MODELS.md#opt-in-live-verification).
Use migrations for schema changes; never substitute ORM `create_all`. See
[persistence operations](docs/operations/PERSISTENCE.md) for transaction boundaries.
