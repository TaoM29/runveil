# Phase 8B handoff — controlled code-reading benchmark

Implemented 2026-10-01 from clean source `1b1fbca`, after inspecting Phase 8A,
AGENTS.md, the charter's evaluation/benchmark/split requirements, roadmap,
architecture, ADR 0029, development guidance, CI and existing evaluator/tests.
The user explicitly authorized the next focused slice. No commit or push.

## Implementation and decisions

Added a frozen **24-case Python code-reading corpus** across eight subjects:
defaults, branches, collections, strings, iteration, exceptions, scope and source
inspection. The 16 development and 8 held-out tasks have disjoint IDs, source and
questions, reviewed exact answers and explicit read/search sequences. The
[inventory](BENCHMARK.md) explains every answer without executing fixture source.

The CLI adds `--suite code-reading` and `--split development|held-out`; defaults
preserve the original calibration and development selection. Unsupported combinations
fail before creating a report or database state. Existing comparison guards use
split-inclusive suite digests and reject mixed or relabeled partitions. Each report
contains one complete partition, not a pooled score. The three/five-step configurations,
claimed execution, exact scorer, fresh public fixture directories and read-only
permissions remain unchanged. No dependency, migration or runtime-policy changes.

[ADR 0030](../adr/0030-controlled-code-reading-benchmark.md) records partition usage
and frozen-content discipline. Public held-out scripts are reserved from tuning,
not secret or contamination-free. Offline checks of both partitions verify plumbing;
no held-out model assessment or prompt/provider optimization occurred. Scripts know
the answers, so the measured differences are known budget effects, not model quality.

## Files created

- `packages/evaluations/src/runveil_evaluations/benchmark.py`: corpus and closed suite selection.
- `docs/adr/0030-controlled-code-reading-benchmark.md`
- `docs/operations/BENCHMARK.md`
- `docs/operations/PHASE_8B.md`
- `docs/operations/evidence/phase8b/development.json`
- `docs/operations/evidence/phase8b/held-out.json`
- `docs/operations/evidence/phase8b/acceptance.json`

## Files modified

- `packages/evaluations/src/runveil_evaluations/contracts.py`: held-out split label.
- `packages/evaluations/src/runveil_evaluations/runner.py`: reuse the comparison runner for a selected suite.
- `packages/evaluations/src/runveil_evaluations/__main__.py`: closed CLI selection and actual denominators.
- `packages/evaluations/tests/test_contracts.py`: one corpus integrity/selection check.
- `packages/persistence/tests/test_evaluations.py`: one full-corpus database/partition check.
- `ARCHITECTURE.md`, `ROADMAP.md`, `docs/operations/DEVELOPMENT.md`,
  `docs/operations/EVALUATIONS.md`: current scope, selection and review gate.

The charter, original calibration content/evidence, manifest/lockfiles and existing
execution/security/telemetry implementations remain unchanged.

## Verification

Commands ran from the root with uv 0.12.19, Python 3.12.14 and Node 24.19.0.
Task-owned PostgreSQL used Compose project `runveil-phase8b`, loopback port 55438,
explicit public local-only credentials, and `--env-file /dev/null`. Integration
tests create their own migrated random databases. No existing database was reset.

```sh
uv sync --locked --all-packages
npm ci
export POSTGRES_USER=runveil POSTGRES_DB=runveil
export POSTGRES_PASSWORD=runveil-local-only POSTGRES_PORT=55438
docker compose --env-file /dev/null -p runveil-phase8b config --quiet
docker compose --env-file /dev/null -p runveil-phase8b up -d --wait --wait-timeout 90
export DATABASE_URL='postgresql+psycopg://runveil:runveil-local-only@127.0.0.1:55438/runveil'
export RUNVEIL_TEST_DATABASE_URL='postgresql+psycopg://runveil:runveil-local-only@127.0.0.1:55438/postgres'
uv run alembic upgrade head
uv run alembic check
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest packages/evaluations/tests packages/persistence/tests/test_evaluations.py --tb=short -q
uv run pytest --tb=short
uv run python scripts/phase5_acceptance.py
npm run format:check
npm run lint
npm run typecheck
npm test
npm run build
uv run python scripts/smoke.py
uv run python -m runveil_evaluations --suite code-reading --output docs/operations/evidence/phase8b/development.json
uv run python -m runveil_evaluations --suite code-reading --split held-out --output docs/operations/evidence/phase8b/held-out.json
git diff --check
```

Locked installs, migrations and all checks passed. Alembic reported no pending
schema operations. Ruff formatting/lint and strict mypy passed (111 source files).
Focused evaluation checks passed **5 tests**; the complete suite passed **298 tests**
(including PostgreSQL integration) in 118.70 seconds. Process-death acceptance passed
checkpoint recovery, uncertain-intent failure and duplicate acknowledgement. Frontend
formatting, lint, types, **11 tests**, production build and real HTTP smoke checks passed.
No live service/provider credentials were used.

A temporary Python acceptance controller invoked the same `python -m
runveil_evaluations --suite code-reading --output <fresh temporary path>` command
in a new process, parsed the reports and compared deterministic case fields. It also
invoked `--split held-out` with the default calibration suite (exit 2, no output) and
retried the existing development output (exit 1, original bytes retained). Direct
SQLAlchemy reads reconciled all **80** persisted runs across development, held-out
and the development repeat with immutable configurations, statuses, invocation
counts and checkpoint accounting. The total remained 80 after both refusals.
The controller and repeat output lived only in temporary storage; its selected
assertions and repeat batch IDs are retained in `acceptance.json`.

Early static checks caught a tuple-length inference issue and one long literal;
explicit variable typing and a source-preserving line split resolved them before
integration acceptance. No corpus values were changed in response to held-out
execution results.

Only two tests were added. The static check parses source as data (never executes
it), checks frozen digests, unique content/IDs/tasks, bounded full reads, unique search
locations and supported selections. One integration test executes all 24 cases
against both budgets, checks each grade/count/denominator, round-trips reports and
rejects cross-split comparisons/relabeling. Existing calibration repeatability,
wrong-answer, missing-read, traversal and mutation-rejection tests still pass.

## Retained evidence

- [Development report](evidence/phase8b/development.json): **8/16 → 16/16**;
  48 → 64 steps, 32 → 40 model intents and 16 → 24 tool intents.
- [Held-out report](evidence/phase8b/held-out.json): **4/8 → 8/8**;
  24 → 32 steps, 16 → 20 model intents and 8 → 12 tool intents.
- [Acceptance record](evidence/phase8b/acceptance.json): fresh CLI repetition,
  split/content/implementation identities, persisted accounting reconciliation,
  exclusive-output and invalid-selection boundary checks.

Both baselines fail only search/read tasks with `step_limit_exceeded`; every
candidate case passes. Usage/pricing is synthetic and unknown counters are zero.
A second development CLI batch reproduces grades, errors, event positions, steps,
intent counts, retries and accounting, excluding run IDs and timestamps/timing.
Repeated execution is reproducibility verification, not additional independent
samples or a reason to increase the reported case denominator.

The task-owned verification database/container/volume are removed after acceptance;
retained run IDs identify the evidence but will not resolve after cleanup. Reproduction
creates fresh IDs. No live provider, AWS, code execution or new browser acceptance.

## Remaining limits and next slice

24 code-reading cases meet the chosen corpus size, not an end-to-end coding-agent
claim. There is no generated repair, test-suite execution, regression-safety oracle,
held-out secrecy, model-generalization measurement, statistical inference, provider
selection expansion, batch resumption or evaluation-table persistence. Existing
local-report interruption and timing/fingerprint limits remain documented.

Review 8B, then perform a focused Phase 8 acceptance/scope audit against the charter,
including the limits of scripted comparisons and any remaining provider-selection
requirements. Keep sandboxed coding and Phase 9 statistics separate. Stop for review;
no automatic continuation, commit or push is authorized.
