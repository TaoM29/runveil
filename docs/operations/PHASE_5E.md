# Phase 5E handoff — pinned pricing and cost budgets

Implemented 2026-09-29; stopped for review. No commit or push.

## Scope and decisions

Inspected the clean repository, AGENTS.md, charter, architecture, roadmap,
relevant accepted ADRs and completed Phase 5D runtime/store/worker/tests.
Implemented the recommended pricing/cost slice with no new dependency or migration.
Also corrected stale Phase 5C status headings/links in README and architecture.

Configuration/checkpoint version 6 pins a complete linear USD price snapshot,
provider/request-model identity and a positive cost limit. Rates and amounts use
integer nano-USD, with no floating point or per-attempt rounding. Invalid, missing
or mismatched prices reject configuration before execution. Explicit zero rates
are allowed; unknown usage remains incomplete even with zero rates.

Checkpoint cost derives from cumulative known input/output usage. Failed attempts,
partial usage, retries, uncertain intent and elapsed expiry share existing
transaction boundaries. Recovery verifies the amount against the pinned rates;
outcomes cannot reset it. Cost exhaustion rejects actions, including finish,
before any further dispatch, and atomically records failure and a budget event.
Token unknown/limit and elapsed/interruption precedence remains documented.

The new offline `fixture-cost-v1` profile uses synthetic usage and prices. Older
profiles keep their behavior, with no retroactive pricing. See
[ADR 0015](../adr/0015-pinned-cost-budget.md) and
[worker operations](WORKER.md#pinned-pricing-and-cost-limits).

## Files

Created:

- `docs/adr/0015-pinned-cost-budget.md`
- `docs/operations/PHASE_5E.md`
- `packages/persistence/tests/test_cost_budget.py`

Modified:

- `packages/agent_core/src/runveil_core/runtime.py`: pricing/cost contracts,
  exact accounting, version-6 validation and budget decision.
- `packages/persistence/src/runveil_persistence/execution.py`: cost validation,
  initial/recovered checkpoints, expiry retention, retry and terminal boundaries.
- `apps/worker/src/runveil_worker/worker.py`, `__main__.py`: fixed cost profile.
- `packages/agent_core/tests/test_runtime_policy.py`: pricing bounds/identity,
  exact arithmetic and unknown/zero-rate semantics.
- `packages/persistence/tests/test_token_budget.py`: reuse existing recovery,
  retry, rollback, stale-owner and expiry cases for the cost profile.
- `README.md`, `ARCHITECTURE.md`, `ROADMAP.md`, `docs/operations/RUNTIME.md`,
  `docs/operations/WORKER.md`: current status, operations and limits.

## Verification

Python 3.12, uv 0.12.19, Node 24.19.0; disposable PostgreSQL 17.9 via Compose
project `runveil-phase5e`, port 55435. No live or paid model calls.

- `uv sync --locked --all-packages`, `npm ci` — passed; manifests/locks unchanged.
  npm reported zero vulnerabilities, with existing ESLint deprecation and optional
  install-script notices. No script approvals or settings were changed.
- `uv run ruff format --check .`, `uv run ruff check .` — passed.
- `uv run mypy` — passed, 61 source files. An initial test-only reused loop-variable
  typing issue was corrected before the final run.
- Focused policy/token/cost run — 22 passed.
- `RUNVEIL_TEST_DATABASE_URL=…/postgres uv run pytest -q` — **224 passed**, including
  **98 PostgreSQL integration cases**. Coverage includes exact/crossed cost limits,
  tool/finish rejection, partial consumption, priced failed attempts across retries,
  fresh-engine recovery, uncertain intent, stale ownership, rejected inconsistent
  outcome cost, atomic rollback and elapsed expiry with retained cost.
- `DATABASE_URL=…/runveil uv run alembic upgrade head`, `uv run alembic check` —
  passed; no new upgrade operations.
- `npm run format:check`, `npm run lint`, `npm run typecheck`, `npm test`,
  `npm run build` — passed; one web test.
- `uv run python scripts/smoke.py` with database configured and with `DATABASE_URL`
  unset — API/web health, production home page and readiness contracts passed.
- Separate CLI processes submitted `fixture-cost-v1`, then three eligible
  `work --once` calls returned RETRYING (steps/retries 1/1), RETRYING (2/2),
  SUCCEEDED (5/2). Repeat delivery returned `no_eligible_work`. Direct checkpoint
  inspection confirmed 20 input/10 output tokens, four model attempts,
  **50,000 nano-USD**, and zero unknown attempts.
- `git diff --check` — passed.

Zero test databases remained. The disposable Compose service and volume were
removed after verification. Other services and local environment files were untouched.

## Remaining concerns and next slice

This is a reproducible linear-price estimate, not an invoice or hard spending cap.
A call may overshoot the threshold. Cache tiers, request fees, reasoning surcharges,
exchange rates and richer billing dimensions are unsupported; no live prices are
fetched. Hosted retry/idempotency, repository workspace identity, broker delivery,
separate model/tool invocation limits and existing cooperative deadline/lease
limitations remain open. Phase 5 is not declared complete.

Review Phase 5E, then implement a small durable repeated-action limit to bound
obvious loops across recovery. Avoid semantic loop inference or expanding tool
capabilities. Mutations, approvals and MCP remain in their planned phases.
