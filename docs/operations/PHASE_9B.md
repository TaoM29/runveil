# Phase 9B handoff — statistical acceptance and scope audit

Acceptance completed 2026-10-01 at `65b14ae`; ready for closure review. Repository
state was clean before this audit. No application, benchmark, dependency or test
changes were necessary. No commit or push was made.

## Audit result and decisions

The [closure assessment](PHASE_9.md) maps every Phase 9 charter requirement to
implementation and evidence. Exact paired percentile resampling is correct for
binary outcomes within the existing 30-case cap. Latency/cost summaries and failure
categories retain complete denominators and existing meanings. Reports reproduce
while runtime identities and timings vary. The scope remains scripted method
validation: no model-quality, significance or population-coverage claim is justified.

The audit used independent arithmetic and direct raw database reads rather than
only calling production aggregators/scorers. Comparison guards and report rebuilding
were checked separately. Existing tests supply regression/security evidence; the
additional audit was temporary acceptance tooling, not new product functionality
or a permanent expansion of the test suite. No new ADR was needed because ADR 0031
already defines the method, output and boundaries.

## Files created

- `docs/operations/PHASE_9.md`: charter-to-evidence assessment and scoped closure.
- `docs/operations/PHASE_9B.md`: this handoff.
- `docs/operations/evidence/phase9b/audit.json`: retained hashes, independent checks,
  repeat fingerprints/run IDs, summaries, guards and reconciliation counts.
- `docs/operations/evidence/phase9b/calibration.json`: fresh full statistical report.
- `docs/operations/evidence/phase9b/development.json`: fresh full development report.
- `docs/operations/evidence/phase9b/held-out.json`: fresh full held-out report.

## Files modified

- `README.md`: correct the stale statement that all evaluation is future work;
  describe implemented scripted evaluation/statistics with their limits.

- `ROADMAP.md`: 9B acceptance gate, scoped closure and recommended Phase 10 review step.
- `ARCHITECTURE.md`: current status and closure evidence; no new boundary.
- `docs/operations/STATISTICS.md`: start-to-finish elapsed semantics and acceptance link.
- `docs/operations/DEVELOPMENT.md`: closure audit link.

The charter, ADRs, Phase 9A handoff and historical JSON evidence are preserved.

## Verification commands and results

Used uv 0.12.19, Python 3.12.14 and Node 24.19.0 for documentation formatting.
Task-owned Compose project `runveil-phase9b` used loopback port 55440 and public
local-only credentials; `.env` loading was disabled. The project had its own fresh
volume. Migrations completed before any evaluation CLI was launched. Existing
integration tests created/migrated/dropped their own random databases.

```sh
uv sync --locked --all-packages
uv run ruff format --check .
uv run ruff check .
uv run mypy
export POSTGRES_USER=runveil POSTGRES_DB=runveil
export POSTGRES_PASSWORD=runveil-local-only POSTGRES_PORT=55440
docker compose --env-file /dev/null -p runveil-phase9b up -d --wait --wait-timeout 90
export DATABASE_URL='postgresql+psycopg://runveil:runveil-local-only@127.0.0.1:55440/runveil'
export RUNVEIL_TEST_DATABASE_URL='postgresql+psycopg://runveil:runveil-local-only@127.0.0.1:55440/postgres'
uv run alembic upgrade head
uv run alembic check
uv run pytest packages/evaluations/tests packages/persistence/tests/test_evaluations.py -q --tb=short
export RUNVEIL_AUDIT_COMMIT="$(git rev-parse HEAD)"
uv run python /tmp/runveil-phase9b-audit.py
npm run format:check
git diff --check
docker compose --env-file /dev/null -p runveil-phase9b down --volumes
```

Locked installation, Ruff formatting/lint and strict mypy (113 source files)
passed. Migration upgrade/check passed with no pending operations. All **seven
existing evaluation tests passed in 25.98 seconds**, including durable scoring,
read-only boundaries, both corpus partitions and the statistical projections.
Documentation formatting and diff whitespace checks passed.

The temporary audit controller completed in one attempt and:

1. Compared the bootstrap output against independent multinomial-composition weights
   for all **5,455** negative/neutral/positive histograms from 1–30 pairs. Checked
   total probability weight, bounds, signed delta, counts and degeneracy. Four
   small ordered-resample enumerations also checked the independent oracle.
2. Verified invalid input rejection for empty, mismatched, oversized, integer and
   null outcomes, and pairing-sensitive equal-marginal examples. Synthetic summary
   checks covered all failure grades, even/odd medians, all-failed denominators,
   partial/all-case unknown costs, and negative/nonfinite elapsed refusal.
3. Parsed the four historical comparison artifacts, recomputed all aggregate fields,
   suite digests and statistical fields, and recorded SHA-256 hashes. Phase 9A's
   implementation fingerprint matches the current code/dependency fingerprint.
4. Launched fresh `python -m runveil_evaluations --statistics --output <new-path>`
   twice for each of calibration, `--suite code-reading` and
   `--suite code-reading --split held-out`. Each batch ran in a separate process.
   Also launched a fresh default-format calibration without `--statistics`.
5. Reconciled **114** fresh runs directly with immutable version/configuration rows,
   terminal status and timestamps, event watermarks, latest checkpoint state and
   raw model/tool invocation rows. Regraded from stored final summaries and ordered
   tool outcomes without calling the production scorer or trace projection.
6. Compared deterministic case fields, configurations, suite and implementation
   identity across repeats. Statistics match exactly; identities and wall times
   were deliberately excluded. Current calibration matches Phase 9A; corpus case
   results match Phase 8B after excluding the expected fingerprint change as well.
7. Refused nine comparison incompatibilities: cross-split, relabelled split, changed
   content, changed implementation, missing/reordered/duplicated coverage, reused
   execution ID and identical agent-version ID. Recomputed tampered cached metrics.
8. Confirmed real CLI refusal of existing files and symlinks (exit 1) and unsupported
   calibration/held-out selection (exit 2). Original bytes and the **114-run** count
   were unchanged; invalid selection created no output. Historical hashes still match.

The first full report for each suite is retained. Repeat reports and the extra
default report were temporary; their deterministic fingerprints, selected summaries,
repeat run IDs and reconciliation verdicts are recorded in the audit JSON. New
report formatting was normalized with Prettier, with semantic JSON identity checked
before/after. The audit records both original CLI-byte hashes and final retained-file
hashes; historical evidence was not reformatted.

The audit controller was temporary and removed after evidence export; its source
hash is retained as provenance, not a substitute for a reproducible tool. To repeat
the acceptance, generate the three report types twice into new paths after migration,
apply the independent multinomial formula and exact quantile rule in the closure
assessment, recompute summaries from case JSON, and reconcile database fields before
removing the disposable database. The seven existing tests remain the repeatable CI
checks. The checked-in reports and audit contain the concrete inputs/results for
independent arithmetic inspection without a database.

## Verification limits and remaining concerns

This docs/evidence-only audit did not rerun the full 300-test suite, process-death
acceptance, frontend lint/types/tests/build, HTTP smoke or browser acceptance.
Phase 9A records those checks for unchanged application source; this audit does not
claim they ran again. No paid/hosted model, AWS, model-selected shell or source-fixture
execution occurred. The disposable verification database and volume were removed;
retained run IDs are historical evidence references, not live trace links.

Historical database authenticity cannot be recovered from unsigned JSON. The Phase
9A initial safe CLI abort cannot be diagnosed from its retained record; all seven
fresh CLI batches here succeeded, but that does not prove the earlier cause.

Intervals are exact empirical bootstrap calculations, not exact-coverage intervals.
Small curated scripted samples, related subjects and no repeated stochastic model
trials limit interpretation. A public held-out partition is not a blind evaluation.
Failure categories follow scorer precedence rather than root-cause analysis. Costs
are synthetic and elapsed summaries include storage/wait time. These limits are
explicit in the closure and methodology; they do not block the scoped method gate.

## Recommended next slice

Review Phase 9 closure, then separately authorize a focused Phase 10 sandbox boundary
slice. Inspect the charter's disposable-workspace, constrained execution and approval
requirements before deciding that slice. Stop for review; no automatic continuation,
commit or push.
