# Contributing

Read the project charter, architecture and roadmap before a change. Inspect the
repository at the start of each phase. Keep work within the approved slice and
record meaningful architecture changes in `docs/adr` before implementing them.

Follow the README quickstart and run its complete quality-check sequence. Use
`uv sync --locked --all-packages` and `npm ci` for normal setup. When intentionally
changing dependencies, update the manifest and lockfile together (`uv lock` or
`npm install`), and verify locked installs again. Format with `uv run ruff format .`
and `npm run format`. The original charter is preserved verbatim and excluded from
Prettier. Keep all commands runnable from the repository root.

Tests must be deterministic and offline once dependencies are installed. Future
live provider tests must be separate and opt-in. Do not add speculative runtime
interfaces, empty Python packages or paid API calls to the foundation.

Never commit `.env`, credentials or generated dependencies. At each handoff report
changes, files, architectural decisions, exact verification results, remaining
concerns and one next slice. Do not claim checks that were not run. Commit and push
only with explicit authorization.
