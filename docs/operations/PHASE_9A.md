# Phase 9A handoff — paired statistical reporting

Implemented 2026-10-01; ready for review. No commit or push. The user authorized
Phase 9 after Phase 8 closure. Repository state was clean at `39542cc`; charter,
architecture, roadmap, ADRs 0029–0030, Phase 8 implementation/tests and closure
records were inspected before choosing this statistical-method slice.

## Implementation and decisions

- Added opt-in statistical JSON generation over the same durable evaluations.
  The default Phase 8 format and all historical artifacts remain unchanged.
- Exact paired empirical bootstrap of binary success deltas computes nominal 95%
  percentile bounds without RNG or dependencies. All-case pairing is preserved;
  identity, implementation, ordered coverage and execution/version guards rerun.
- Added mean/median persisted elapsed time, mean known cost, nullable complete cost,
  unknown counters, failure categories and explicit scripted interpretation.
- Added two focused synthetic/report tests and assertions in existing real-database
  acceptance. No runtime, tool, provider, persistence, authentication, approval,
  telemetry, frontend, benchmark, manifest or lockfile changes.

[ADR 0031](../adr/0031-exact-paired-statistics.md) records the algorithm and limits;
[methodology](STATISTICS.md) defines units, quantiles, pairing and interpretation.
No McNemar p-value or automated promotion gate is justified by scripted data.

## Files created

- `packages/evaluations/src/runveil_evaluations/statistics.py`
- `packages/evaluations/tests/test_statistics.py`
- `docs/adr/0031-exact-paired-statistics.md`
- `docs/operations/STATISTICS.md`
- `docs/operations/evidence/phase9a/calibration.json`
- `docs/operations/PHASE_9A.md`

## Files modified

- `packages/evaluations/src/runveil_evaluations/__main__.py`: opt-in flag and wrapper.
- `packages/persistence/tests/test_evaluations.py`: durable statistical projection assertions.
- `ARCHITECTURE.md`, `ROADMAP.md`: implemented boundary, review gate and next slice.
- `docs/operations/EVALUATIONS.md`, `docs/operations/DEVELOPMENT.md`: usage links.

## Verification

Used uv 0.12.19, Python 3.12.14 and Node 24.19.0 (explicitly selected instead of the
shell's Node 20 default). Task-owned Compose project `runveil-phase9a` used loopback
55439, public local-only credentials and no `.env` loading. No existing user database
was reset. Integration tests use their usual isolated randomly named databases.

Commands executed from the repository root:

```sh
uv sync --locked --all-packages
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest -m 'not integration'
export POSTGRES_USER=runveil POSTGRES_DB=runveil
export POSTGRES_PASSWORD=runveil-local-only POSTGRES_PORT=55439
docker compose --env-file /dev/null -p runveil-phase9a up -d --wait --wait-timeout 90
export DATABASE_URL='postgresql+psycopg://runveil:runveil-local-only@127.0.0.1:55439/runveil'
export RUNVEIL_TEST_DATABASE_URL='postgresql+psycopg://runveil:runveil-local-only@127.0.0.1:55439/postgres'
uv run alembic upgrade head
uv run alembic check
uv run pytest -m integration
uv run python scripts/phase5_acceptance.py
uv run python -m runveil_evaluations --statistics --output docs/operations/evidence/phase9a/calibration.json
npm ci
npm run lint
npm run typecheck
npm test
npm run build
uv run python scripts/smoke.py
npm run format:check
git diff --check
docker compose --env-file /dev/null -p runveil-phase9a down --volumes
```

Results: locked install, Ruff and strict mypy (113 files) passed. All **300 Python
tests passed**: 142 offline tests in 7.66 seconds and 158 integration tests in
108.38 seconds. Migration upgrade/check passed with no pending operations.
Process-death acceptance passed checkpoint recovery, uncertain-intent failure,
active-lease deferral and duplicate acknowledgement, then removed its database.
Frontend lint/types, all **11 tests**, production build and HTTP smoke passed.
Smoke was run both without and with the database URL, verifying both readiness
branches. No new browser acceptance was run because no UI changed.

Synthetic oracles exhaustively enumerate small paired resamples independently of
the convolution algorithm, including mixed discordance, ties, constant outcomes,
one pair, pairing-sensitive equal marginals and the 30-pair boundary. Report tests
check recomputation, incompatible evidence, unknown costs and separate failures.
Existing database tests still cover the full 24-case corpus, separate splits,
scoring, traversal/write refusal and immutable agent configuration.

The retained fresh CLI calibration has 2/3 baseline versus 3/3 candidate, one
improved pair, delta 1/3, nominal bounds [0, 1], and candidate mean synthetic cost
40,000 nano-USD. A temporary independent JSON check recomputed paired samples,
mean/median time and mean cost directly from case data. CLI overwrite refusal
returned 1 with original bytes intact; invalid calibration/held-out selection
returned 2 with no output. These checks used the actual CLI, not a mock.

An initial CLI invocation during concurrent verification startup aborted with the
existing safe generic error and left an empty output file. The two subsequent
fresh batches succeeded; the database contained exactly their 12 terminal runs
(10 succeeded, 2 expected budget failures), so the aborted attempt created no
runs. The precise initial exception was not retained; startup timing is not a
confirmed diagnosis. The empty artifact was moved outside the repository before
fresh exclusive creation. It is not acceptance evidence. No implementation change
was needed for the successful retries. Historical reports were never overwritten.

## Remaining concerns and next slice

Intervals describe resampling of a tiny curated scripted sample; they do not
establish model quality, generalization, statistical significance or population
coverage. Related cases violate simple independent-sample interpretations. Constant
observed effects yield degenerate bounds, explicitly marked. No repeated stochastic
trials, cluster adjustment, BCa, inference test or cost/latency uncertainty is added.

JSON evidence is not signed or authenticated; durable execution remains authoritative.
The disposable verification database is removed after checks, so retained run IDs
are historical references. No paid provider, AWS, shell tool or fixture execution
was used. npm installation reported an existing ESLint deprecation and uncovered
install-script policy entries; checks passed and dependencies were not changed.

Recommended next slice: review Phase 9A, then authorize a Phase 9 acceptance/scope
audit against fresh statistical reports before closure or Phase 10. Stop here for
review; no automatic continuation.
