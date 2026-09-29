# Phase 5D handoff — durable reported-token budgets

Implemented on 2026-09-29; stopped for review. No commit or push.

## Scope and decisions

Inspected the clean repository, charter, architecture, roadmap, relevant accepted
ADRs and Phase 5C implementation. The next planned slice was token accounting and
bounded continuation. Version 5 adds strict input/output run limits alongside the
elapsed deadline. Existing worker profiles retain their behavior; the new
`fixture-token-v1` supplies explicit synthetic usage.

Immutable outcome checkpoints carry cumulative known token counts, model-attempt
counts, unknown-attempt counts and nullable latest usage. This reuses the existing
atomic history boundary without a schema migration, dependency or separate ledger.
Failed responses retain usage even when their action content is rejected. Unknown
usage blocks further action/retry. Known failed usage accumulates across retry
claims and new engines. Interrupted model intent records unknown usage once.
Elapsed expiry retains available usage while discarding late content. Ownership
fences and rollback apply to the complete write.

[ADR 0014](../adr/0014-durable-token-budget.md) defines the semantics: reaching a
reported threshold fails before accepting the model action, including a finish
action. One call may cross a threshold; this is not a hard token/billing cap.
Known partial counts remain lower bounds with explicit uncertainty. Cost budgets
and provider-specific pre-dispatch estimation are outside this slice.

## Files

Created:

- `docs/adr/0014-durable-token-budget.md`
- `docs/operations/PHASE_5D.md`
- `packages/persistence/tests/test_token_budget.py`

Modified:

- `packages/agent_core/src/runveil_core/models.py`: optional normalized error usage.
- `packages/agent_core/src/runveil_core/runtime.py`: version-5 limits/accounting,
  fail-closed unknown handling and post-attempt enforcement.
- `packages/persistence/src/runveil_persistence/execution.py`: atomic accounting
  validation, expiry retention, budget events and recovery checks.
- `apps/worker/src/runveil_worker/worker.py`, `__main__.py`: explicit token profile.
- `packages/agent_core/tests/test_runtime_policy.py`: strict version/limit boundary.
- `README.md`, `ARCHITECTURE.md`, `ROADMAP.md`, `docs/operations/WORKER.md`,
  `docs/operations/RUNTIME.md`, `docs/operations/MODELS.md`: current behavior and limits.

## Verification

Using Python 3.12, uv 0.12.19, Node 24.19.0 and disposable PostgreSQL 17.9,
Compose project `runveil-phase5d` on port 55435. No live/paid provider calls.

- `uv sync --locked --all-packages` — passed; no dependency changes.
- `npm ci` — passed, zero reported vulnerabilities. Existing ESLint deprecation
  and optional install-script notices appeared; no approvals/settings changed.
- `uv run ruff format --check .`, `uv run ruff check .` — passed.
- `uv run mypy` — passed, 60 source files.
- `RUNVEIL_TEST_DATABASE_URL=…/postgres uv run pytest -q` — **214 passed**, including
  **90 PostgreSQL integration cases**. New tests cover strict limits, exact/crossed
  thresholds, partial usage, unknown failed attempts, rejected action usage,
  cumulative failed usage across retries, new-engine recovery, uncertain intent,
  stale ownership, rollback and late-usage retention.
- Initial full run caught a test setup mismatch in advertised tools between retry
  requests; corrected the fixture to preserve the existing request identity guard.
- `DATABASE_URL=…/runveil uv run alembic upgrade head` and `uv run alembic check` —
  passed, no new upgrade operations.
- `npm run format:check`, `npm run lint`, `npm run typecheck`, `npm test`,
  `npm run build` — passed; one web test.
- `uv run python scripts/smoke.py` with database configured and with `DATABASE_URL`
  unset — API/web health, production home page and readiness contracts passed.
- Separate CLI processes: token-profile submit, three eligible `work --once`
  calls produced RETRYING (1/1), RETRYING (2/2), SUCCEEDED (5/2); repeat delivery
  returned `no_eligible_work`. Stored totals: 20 input, 10 output, four model
  attempts, zero unknown attempts.
- `git diff --check` — passed.

The disposable database had zero leftover test databases and was removed with its
volume after verification. Other running services and local environment files
were not changed.

## Remaining concerns and next slice

Usage reports are trusted provider evidence; missing usage cannot establish an
exact total. External dispatch is still non-atomic with lease ownership and a
single request can overshoot a reported threshold. Existing cooperative-deadline
and 660-second crash-cleanup lease limitations remain. No hosted replay, workspace
recovery, approvals, mutation or cost accounting is introduced.

Review Phase 5D, then define pinned pricing and durable cost accounting/budgets
with explicit unknown-usage/pricing behavior. Keep hosted calls opt-in and reuse
the existing outcome boundaries.
