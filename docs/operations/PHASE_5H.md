# Phase 5H handoff — pinned repository recovery

Implemented 2026-09-29; stopped for review. No commit or push.

## Scope and decisions

Inspected the clean repository, AGENTS.md, charter, architecture, roadmap,
relevant accepted ADRs and completed runtime/store/worker/repository implementation.
The next planned slice was workspace and implementation identity for bounded
read-only repository recovery. The current request authorizes continuation beyond
the charter's historical Phase 0 instruction and the Phase 5G review gate.

Explicit snapshot mode captures the complete sorted allowlist using existing
filesystem checks, bounded to 128 files, 64 KiB each and 1 MiB total. Read/search
then use immutable in-memory strings; descriptors close after capture. Default
live bindings retain their behavior. Version 9 pins three SHA-256 fingerprints:
canonical root path/device/inode, selected paths/content, and covered source
modules plus Python/Pydantic versions. The store requires an expected configuration
and rejects mismatch before model/tool dispatch or history writes.

The new `repository-read-v1` profile captures at submission and each work invocation.
Its fixed offline provider reads the first excerpt of the first sorted file and
finishes with synthetic usage/pricing. CLI work requires explicit root/files,
`--once` and `--run-id`. Existing budgets, leases, checkpoints and conservative
uncertain-intent handling remain authoritative. No migration or external dependency
was added; the worker now depends on the existing tool-runtime workspace package.
See [ADR 0018](../adr/0018-pinned-repository-recovery.md) and
[worker operations](WORKER.md#pinned-repository-recovery).

## Files

Created:

- `apps/worker/src/runveil_worker/repository_worker.py`: fixed profile, submission,
  snapshot binding and one-run work entry point.
- `packages/persistence/tests/test_repository_worker.py`: recovery and binding drift.
- `docs/adr/0018-pinned-repository-recovery.md` and this handoff.

Modified:

- `packages/agent_core/src/runveil_core/runtime.py`: version-9 identity/configuration.
- `packages/persistence/src/runveil_persistence/execution.py`: required binding check.
- `packages/tool_runtime/src/runveil_tools/filesystem.py`, `repository.py`: root
  identity, bounded snapshot capture, implementation fingerprint and captured reads.
- `packages/tool_runtime/tests/test_repository.py`: snapshot stability, full-allowlist
  validation and aggregate bound.
- `apps/worker/src/runveil_worker/__main__.py`: explicit repository CLI binding.
- `apps/worker/pyproject.toml`, `uv.lock`: workspace dependency.
- `README.md`, `ARCHITECTURE.md`, `ROADMAP.md`, `docs/operations/RUNTIME.md`,
  `docs/operations/WORKER.md`, `docs/operations/REPOSITORY_TOOLS.md`: status and boundaries.

## Verification

Python 3.12, uv 0.12.19, Node 24.19.0; disposable PostgreSQL 17.9, Compose project
`runveil-phase5h`, port 55435. All repository fixtures contain public synthetic text.
No live/paid provider calls or real checkout disclosure.

- `uv sync --locked --all-packages`, `npm ci` — passed. npm reported zero
  vulnerabilities and existing ESLint deprecation/optional install-script notices;
  no approval settings changed.
- `uv run ruff format --check .`, `uv run ruff check .`, `uv run mypy` — passed;
  65 strictly checked source files.
- Focused repository and repository-worker tests — 18 passed.
- `RUNVEIL_TEST_DATABASE_URL=…/postgres uv run pytest -q` — **248 passed**, including
  **117 PostgreSQL integration cases**. New cases verify immutable reads/search after
  disk edits, unchanged identity after allowlist reorder/unselected edits, full
  capture refusal for links/aggregate overflow, refusal of missing expected binding,
  changed root/root replacement/allowlist/content/implementation, unchanged history
  and no dispatch on mismatch, and fresh-engine recovery before/after a committed
  read with one retained tool result. Existing uncertain-intent/ownership/budget
  tests also passed; they were not duplicated for this fixed profile.
- `DATABASE_URL=…/runveil uv run alembic upgrade head`, `uv run alembic check` —
  passed; no new upgrade operations.
- `npm run format:check`, `npm run lint`, `npm run typecheck`, `npm test`,
  `npm run build` — passed; one web test.
- `uv run python scripts/smoke.py` with database configured and with `DATABASE_URL`
  unset — API/web health, production home page and readiness contracts passed.
- Separate CLI processes submitted `repository-read-v1` against a temporary public
  file and ran `work --once --run-id`: `SUCCEEDED steps=3 retries=0`. Repeat delivery
  returned `no_eligible_work`. Persisted evidence verified schema 9, two model calls,
  one tool result, 20 input/10 output tokens and 50,000 nano-USD. Missing binding or
  explicit work selection rejected with exit 2 and no traceback.
- `git diff --check` — passed.

Zero test databases remained. The disposable Compose service and volume were
removed after verification. Other services and local environment files were untouched.

## Remaining concerns and next slice

The snapshot is not a durable content archive or atomic Git revision. Recovery
requires identical selected bytes at the same canonical root/device/inode; active
snapshots intentionally ignore later disk edits. Operators must approve disclosure
and keep selected files stable during capture. Covered source formatting changes
also invalidate recovery; the fingerprint is not full dependency attestation and
requires source-backed installations. Versioned provider semantics still depend on
maintaining profile IDs. Trusted Python can bypass adapter contracts.

Mismatch may leave the claimed lease until expiry and the existing execution
deadline keeps running. Native filesystem calls remain cooperatively cancellable,
not forcibly terminable. No hosted recovery, mutation, broker or tool replay is
introduced; Phase 5 is not declared complete.

Review Phase 5H, then define and implement the broker/database delivery consistency
boundary for an offline-tested SQS adapter, including enqueue/outbox, duplicates
and acknowledgement with PostgreSQL ownership authoritative. Hosted retries need
a separate provider safety/idempotency policy; approvals and MCP stay in later phases.
