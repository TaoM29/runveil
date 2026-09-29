# Phase 5G handoff — separate model/tool call limits

Implemented 2026-09-29; stopped for review. No commit or push.

## Scope and decisions

Inspected the clean repository, AGENTS.md, charter, architecture, roadmap,
relevant accepted ADRs and completed runtime/store/worker implementation. The
next planned slice was independent run-wide model/tool invocation limits.

Version 8 pins `max_model_calls` and `max_tool_calls` (strict integers 0–64),
alongside existing budgets. Zero disables a kind. Admission counts durable
invocation records under the existing ownership/history locks, before creating
another intent. All statuses consume capacity, including failed and uncertain
attempts. The repeated-tool admission path shares the same atomic failure helper;
no mutable counters, dependencies or migration were added.

Successful finish at the exact limit remains valid. An otherwise eligible retry
without remaining model capacity fails in its outcome transaction, without
backoff or RETRYING. Its invocation retains the provider error while the run
records `model_call_limit_exceeded`. The store also rejects such a retry schedule.
Recovery preserves counts and resolves uncertain intent as `execution_interrupted`.
Existing ownership, cancellation, elapsed, combined-step and usage budget semantics
remain active.

The new offline `fixture-calls-v1` succeeds exactly at two model calls and one
tool call in three steps. Older profiles keep their behavior. See
[ADR 0017](../adr/0017-durable-invocation-limits.md) and
[worker operations](WORKER.md#separate-model-and-tool-call-limits).

## Files

Created:

- `docs/adr/0017-durable-invocation-limits.md`
- `docs/operations/PHASE_5G.md`
- `packages/persistence/tests/test_call_limits.py`

Modified:

- `packages/agent_core/src/runveil_core/runtime.py`: version-8 limits and retry
  capacity decision, retaining the provider's failed-attempt evidence.
- `packages/persistence/src/runveil_persistence/execution.py`: pinned admission
  counts, shared atomic request-budget failure, retry validation and budget events.
- `apps/worker/src/runveil_worker/worker.py`, `__main__.py`: fixed calls profile.
- `packages/agent_core/tests/test_runtime_policy.py`: strict version/limit bounds.
- `README.md`, `ARCHITECTURE.md`, `ROADMAP.md`, `docs/operations/RUNTIME.md`,
  `docs/operations/WORKER.md`: current status, operations and limits.

## Verification

Python 3.12, uv 0.12.19, Node 24.19.0; disposable PostgreSQL 17.9, Compose project
`runveil-phase5g`, port 55435. No live or paid model calls.

- `uv sync --locked --all-packages`, `npm ci` — passed; manifests/locks unchanged.
  npm reported zero vulnerabilities plus existing ESLint deprecation and optional
  install-script notices; no approvals/settings changed.
- `uv run ruff format --check .`, `uv run ruff check .` — passed.
- `uv run mypy` — passed, 63 source files.
- Focused runtime policy/call-limit tests — 15 passed.
- `RUNVEIL_TEST_DATABASE_URL=…/postgres uv run pytest -q` — **238 passed**, including
  **110 PostgreSQL integration cases**. New tests cover zero caps, exact-limit
  finish, independent capacity after another kind reaches its limit, rejection
  before dispatch, fresh-engine recovery, rollback, stale owners, pinned-policy
  enforcement, failed retry accounting without an extra schedule, and uncertain
  model/tool intent recovery without replay.
- `DATABASE_URL=…/runveil uv run alembic upgrade head`, `uv run alembic check` —
  passed; no new upgrade operations.
- `npm run format:check`, `npm run lint`, `npm run typecheck`, `npm test`,
  `npm run build` — passed; one web test.
- `uv run python scripts/smoke.py` with database configured and with `DATABASE_URL`
  unset — API/web health, production home page and readiness contracts passed.
- Separate CLI processes submitted `fixture-calls-v1` and ran `work --once`:
  `SUCCEEDED steps=3 retries=0`; repeat delivery returned `no_eligible_work`.
  Checkpoint/record inspection confirmed two model intents, one tool intent,
  20 input/10 output tokens and 50,000 nano-USD.
- `git diff --check` — passed.

Zero test databases remained. The disposable Compose service and volume were
removed after verification. Other services and local environment files were untouched.

## Remaining concerns and next slice

These caps bound committed intents; they do not guarantee provider-internal attempt
counts, billing or exactly-once external execution. The combined step bound can
terminate first. Conservative uncertain-intent and cooperative deadline/lease
limitations remain. No hosted retries, repository recovery, broker or new tool
side effects are introduced. Phase 5 is not declared complete.

Review Phase 5G, then establish pinned repository workspace/implementation identity
for a bounded durable read-only repository profile. Recovery must not silently
switch its root, allowlist, content snapshot or tool implementation. Broker
consistency and hosted retry/idempotency remain open; mutations, approvals and MCP
stay in their planned phases.
