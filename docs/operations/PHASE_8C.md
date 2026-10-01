# Phase 8C handoff — acceptance and scope audit

Audited 2026-10-01 from clean source
`2e385b808298466d858b4d0f829b441d7d54db0c`. Followed AGENTS.md, charter evaluation
requirements, accepted ADRs 0029–0030, architecture, roadmap, development guide and
CI. Inspected the completed evaluator, corpus, existing tests and retained 8A/8B
reports before making changes. No commit or push.

## Outcome and scope decision

The [closure audit](PHASE_8.md) recommends accepting Phase 8 within its documented
offline scripted/read-only boundary. It maps every Phase 8 gate to implementation,
evidence and explicit limits. The v1/v2 gate uses two immutable step budgets against
identical cases; a general provider selector is not required to demonstrate that
initial comparison. The broader charter's model-quality and coding/test metrics
remain product work, not claims established by this closure.

No genuine implementation defect was found within that scope. No application,
benchmark, dependency, schema, policy, configuration or test changed. Two inaccurate
documentation claims were corrected: independent human oracle review was not
established, and only search/read candidate cases consume all five allowed steps.
The docs now also distinguish schema/aggregate checks from report authentication.

## Files created

- `docs/operations/PHASE_8.md`: criterion/evidence audit, scoped verdict and limits.
- `docs/operations/PHASE_8C.md`: this handoff.
- `docs/operations/evidence/phase8c/audit.json`: retained-file hashes, selected fresh
  execution results, content/implementation identity, arithmetic/reproducibility,
  comparison guards, direct DB reconciliation and CLI refusal outcomes.

## Files modified

- `ROADMAP.md`: 8C acceptance gate, scoped closure and next review gate.
- `ARCHITECTURE.md`: current heading and closure evidence; no new boundary.
- `docs/adr/0030-controlled-code-reading-benchmark.md`: correct source-review attribution.
- `docs/operations/BENCHMARK.md`: exact-budget wording and closure link.
- `docs/operations/EVALUATIONS.md`: closure link and report verification limits.
- `docs/operations/DEVELOPMENT.md`: closure audit link.

The original charter, historical handoffs and historical JSON evidence are preserved.
The new audit records hashes of the historical files it inspected.

## Verification performed

Used uv 0.12.19, Python 3.12.14 and Node 24.19.0 for documentation formatting.
PostgreSQL was isolated in task-owned Compose project `runveil-phase8c`, loopback
55438, with explicit public local-only credentials and no `.env` loading. Existing
integration tests own randomly named migrated databases. No user's existing database
was reset or removed.

```sh
uv sync --locked --all-packages
uv run ruff format --check .
uv run ruff check .
uv run mypy
export POSTGRES_USER=runveil POSTGRES_DB=runveil
export POSTGRES_PASSWORD=runveil-local-only POSTGRES_PORT=55438
docker compose --env-file /dev/null -p runveil-phase8c config --quiet
docker compose --env-file /dev/null -p runveil-phase8c up -d --wait --wait-timeout 90
export DATABASE_URL='postgresql+psycopg://runveil:runveil-local-only@127.0.0.1:55438/runveil'
export RUNVEIL_TEST_DATABASE_URL='postgresql+psycopg://runveil:runveil-local-only@127.0.0.1:55438/postgres'
uv run alembic upgrade head
uv run alembic check
uv run pytest packages/evaluations/tests packages/persistence/tests/test_evaluations.py --tb=short -q
export RUNVEIL_AUDIT_COMMIT=2e385b808298466d858b4d0f829b441d7d54db0c
uv run python /tmp/runveil-phase8c-audit.py
npm run format:check
git diff --check
docker compose --env-file /dev/null -p runveil-phase8c down --volumes
```

Locked installation, Ruff format/lint, strict mypy (111 files) and migrations passed;
Alembic reported no pending schema operations. The **five existing evaluation tests
passed in 34.72 seconds**, including full-corpus execution and boundary checks.
The final audit controller passed retained arithmetic, all eight comparison guards,
fresh reproduction of both partitions, 48 direct database reconciliations and both
CLI refusal checks. Documentation formatting and `git diff --check` passed.

The temporary audit controller:

1. Parsed all three retained comparison reports and independently recomputed every
   aggregate field and rate delta using case-level JSON, rather than reusing the
   production aggregate helper for that check. Verified suite content, version/split
   digests, and that version configurations differ only by their step limit.
2. Exercised eight comparator refusals: cross-split, relabelled split, changed source,
   missing/reordered coverage, implementation mismatch, reused run ID and identical
   agent-version ID. Existing tests also cover rescoring/version mismatch.
3. Spawned fresh `python -m runveil_evaluations --suite code-reading --split development
--output <temporary>/development.json` and the corresponding `held-out` command.
   Compared every case with retained 8B results excluding only IDs and elapsed time
   (batch metadata/timestamps naturally differ). Current source fingerprint matches 8B.
4. Independently reconciled all 48 fresh runs directly with database configuration,
   status, checkpoint steps/errors/accounting and raw invocation rows. Recomputed
   grades from final summaries and ordered successful tool names without calling
   the production scorer.
5. Refused an existing output path (exit 1, original bytes unchanged) and invalid
   calibration/held-out selection (exit 2, no output). Confirmed the run count stayed 48.
6. Saved hashes/selected evidence to the new audit JSON; no historical report changed.

The controller was temporary acceptance tooling, not a new product command or test.
Its first execution passed the substantive assertions but failed while collecting
Git provenance: macOS Git could not launch under the installed x86_64 Python due
to a CommandLineTools architecture mismatch. The shell independently resolved the
full revision; passing it explicitly fixed evidence export. Only the task-owned
verification database was recreated and migrated for the clean rerun. No benchmark
or application change was made in response. Both partitions were already public
scripted fixtures; repeating them was an audit retry, not tuning or new samples.

The existing five tests remain the repeatable CI verification. To reproduce the
extra retained-artifact checks, parse the original JSON files, recalculate sums,
call the existing comparator on the documented incompatible pairs and generate
fresh reports with the two commands above. Compare deterministic case fields and
inspect raw run/checkpoint/invocation rows before removing the disposable database.
The temporary controller and full temporary reports were removed after evidence
export; selected fresh results and all tested conditions remain in the audit JSON.

## Verification limits and remaining concerns

This docs/evidence-only audit did not rerun the full 298-test suite, process-death
acceptance, frontend lint/types/tests/build, HTTP smoke or browser checks. Their
successful 8B record applies to unchanged application source; it is historical
evidence, not a fresh claim. No network model, paid provider, AWS or fixture-code
execution was used. Formatting/diff checks cover the changed documentation.

Original acceptance databases and full 8B repeat output are gone. The retained
records are not signed attestations; JSON parsing and comparator checks cannot
establish authenticity. Fresh scoped execution supplements those records. The new
disposable database and volume were also removed after verification, so report run
IDs are evidence references rather than live trace links. Timings remain variable.

Public held-out scripts are not blind evaluations. Source-reviewed answers are not
independently human-certified, and scripts sharing their oracle values cannot measure
model quality. Metrics cover the documented harness, not generated coding/test success
or every metric in the overall charter. Phase 9 statistics and Phase 10 sandbox
capabilities remain unimplemented by this work.

## Recommended next slice

Review Phase 8 closure, then explicitly authorize a focused Phase 9 statistical-method
slice with known synthetic paired outcomes. Do not reinterpret scripted rate deltas
as real model improvements. Stop for review; no automatic continuation, commit or push.
