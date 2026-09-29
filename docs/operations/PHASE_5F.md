# Phase 5F handoff — durable repeated-tool limit

Implemented 2026-09-29; stopped for review. No commit or push.

## Scope and decisions

Inspected the clean repository, AGENTS.md, charter, architecture, roadmap,
relevant accepted ADRs and completed runtime/store/worker implementation. The
next planned slice was deterministic repeated-action detection.

Version 7 pins `max_identical_tool_calls` alongside existing budgets. The store
counts prior intents for the same run/tool name/JSONB arguments under its existing
ownership lock, using immutable invocation history. No counter table, checkpoint
counter, dependency or migration was added. JSON object order is irrelevant;
array order matters, numerically equal JSON numbers match and booleans remain
distinct. Intervening actions and model retries do not reset counts.

At the limit, commit the failed checkpoint, budget event and terminal transition
before returning the failed state. No new tool intent is created or dispatched.
The proposing model response and its usage remain committed; the checkpoint
retains the blocked action/source. Rollback leaves the prior checkpoint intact.
Recovery uses the same durable count. Existing ownership, cancellation, elapsed
and total-step boundaries retain their precedence.

The new offline `fixture-loop-v1` deliberately repeats a read-only fixture and
fails before its third identical call. Older profiles keep their behavior. See
[ADR 0016](../adr/0016-durable-repeated-tool-limit.md) and
[worker operations](WORKER.md#repeated-tool-limit).

## Files

Created:

- `docs/adr/0016-durable-repeated-tool-limit.md`
- `docs/operations/PHASE_5F.md`
- `packages/persistence/tests/test_repeated_tools.py`

Modified:

- `packages/agent_core/src/runveil_core/runtime.py`: version-7 configuration and
  common committed-budget exception handling, retaining the elapsed subtype.
- `packages/persistence/src/runveil_persistence/execution.py`: pinned limit lookup,
  history-based admission, atomic failure and version-7 initial cost state.
- `apps/worker/src/runveil_worker/worker.py`, `__main__.py`: loop demonstration profile.
- `packages/agent_core/tests/test_runtime_policy.py`: strict version/limit bounds.
- `README.md`, `ARCHITECTURE.md`, `ROADMAP.md`, `docs/operations/RUNTIME.md`,
  `docs/operations/WORKER.md`: current status, operations and limits.

## Verification

Python 3.12, uv 0.12.19, Node 24.19.0; disposable PostgreSQL 17.9, Compose project
`runveil-phase5f`, port 55435. No live or paid provider calls.

- `uv sync --locked --all-packages`, `npm ci` — passed; manifests/locks unchanged.
  npm reported zero vulnerabilities plus existing ESLint deprecation and optional
  install-script notices; no approvals/settings changed.
- `uv run ruff format --check .`, `uv run ruff check .` — passed.
- `uv run mypy` — passed, 62 source files.
- Focused runtime policy/repeated-tool tests — 10 passed.
- `RUNVEIL_TEST_DATABASE_URL=…/postgres uv run pytest -q` — **229 passed**, including
  **102 PostgreSQL integration cases**. New behavior is covered by one strict
  policy test and four integration cases: recovery after tool/model checkpoints,
  rollback of budget finalization, stale-owner rejection, exact argument/tool
  identity across intervening calls, pinned-policy enforcement and preservation
  of prior tool counts through model retry. Terminal duplicate delivery does no work.
- `DATABASE_URL=…/runveil uv run alembic upgrade head`, `uv run alembic check` —
  passed; no new upgrade operations.
- `npm run format:check`, `npm run lint`, `npm run typecheck`, `npm test`,
  `npm run build` — passed; one web test.
- `uv run python scripts/smoke.py` with database configured and with `DATABASE_URL`
  unset — API/web health, production home page and readiness contracts passed.
- Separate CLI processes submitted `fixture-loop-v1` and ran `work --once`:
  `FAILED steps=5 retries=0`, exit **1 as expected**. Repeat delivery printed
  `no_eligible_work` and exited 0. Checkpoint inspection confirmed
  `repeated_tool_limit_exceeded`, three model attempts, two tool intents,
  30 input/15 output tokens and 75,000 nano-USD.
- `git diff --check` — passed.

Zero test databases remained. The disposable Compose service and volume were
removed after verification. Other services and local environment files were untouched.

## Remaining concerns and next slice

This guard can stop legitimate repeated polling and only matches exact structural
arguments. Changed arguments, different tool names or semantic equivalents have
separate counts; existing step/time/token/cost limits remain the wider bounds.
No tool retry, semantic progress inference or exactly-once side effects is added.
Hosted retry/idempotency, repository workspace identity and broker integration
remain open. Phase 5 is not declared complete.

Review Phase 5F, then implement separate run-wide model/tool invocation limits,
using durable attempt history and preserving total-step, retry and uncertain-intent
semantics. Mutations, approvals and MCP remain in their planned phases.
