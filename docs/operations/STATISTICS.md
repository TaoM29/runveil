# Paired statistical calibration (Phase 9A)

After the normal migrated PostgreSQL setup, generate a new statistical report:

```sh
uv run python -m runveil_evaluations --statistics --output /tmp/calibration-statistics.json
uv run python -m runveil_evaluations --statistics --suite code-reading --split development --output /tmp/development-statistics.json
uv run python -m runveil_evaluations --statistics --suite code-reading --split held-out --output /tmp/held-out-statistics.json
```

The output path must be new. Existing overwrite refusal, safe errors, database
claims, scoring, split selection and complete-case denominators still apply.
Without `--statistics`, the Phase 8 report format is unchanged. With it, a
`paired-statistical-calibration` schema-version-1 wrapper embeds that comparison,
its provenance, `success`, `baseline_summary` and `candidate_summary`. No loader
for external JSON or automatic pass/fail regression gate is added.

## Method

Pair by the existing exact suite identity and ordered case coverage, retaining
runtime failures as failures. Let d_i = candidate_pass_i - baseline_pass_i. The
point estimate is mean(d_i), in rate units; multiply by 100 for percentage points.
The bootstrap samples n paired cases with replacement, preserving both outcomes
of each selected case. Sampling versions independently would discard covariance.

For binary outcomes the differences are -1, 0 or 1. Starting with weight 1 at sum
zero, convolve n times with the observed counts of these three differences. The
integer weight at each sum counts its ordered resamples among n^n equally likely
resamples. This computes the full empirical bootstrap distribution without random
sampling or a seed. Work is bounded by the suite cap of 30 pairs. Quantiles are
the smallest support points whose cumulative probability reaches 1/40 and 39/40;
there is no interpolation. Divide those sums by n to obtain the nominal 95%
percentile interval. The method identifier fixes these conventions.

The bootstrap and percentile principles are described in
[MIT's bootstrap confidence interval notes](https://ocw.mit.edu/courses/18-05-introduction-to-probability-and-statistics-spring-2022/mit18_05_s22_class24-prep.pdf).
The exact integer convolution is our bounded implementation of paired resampling.
Tests independently enumerate all ordered resamples for small synthetic examples.

`improved`, `regressed` and `unchanged` count paired outcomes, including both-pass
and both-fail cases in unchanged. A single distinct observed difference produces
`degenerate: true` and a collapsed interval. This includes all-zero and all-win
samples and is a limitation of the empirical distribution, not proof of certainty.

## Interpretation and summaries

These are scripted harness demonstrations, **not model inference**. The scripts
contain their answers and intentionally differ by a step budget. Curated cases
are not a random sample, related subjects can violate independent-case assumptions,
and public held-out membership is a tuning convention. Exact resampling removes
simulation error; it does not guarantee 95% population coverage. Tiny, discrete
samples can give poor percentile coverage. One run per case cannot estimate
within-case model randomness. No superiority, p-value or significance claim follows
from excluding zero. Review practical effect sizes, failure patterns and the study
design before any future model comparison.

Elapsed summaries are arithmetic mean and median over all cases, including failed
runs. Persisted elapsed time is run start-to-finish wall duration, including storage and
any waiting, and is not provider latency;
sequential baseline/candidate batches are not a controlled performance experiment.
Short failures can misleadingly reduce elapsed time and cost.

Cost summaries are mean known nano-USD per case and the number of unknown attempts.
If any cost attempt is unknown, mean total cost is null; known subtotals remain
visible. Otherwise mean total equals mean known. Current usage and tariffs are
synthetic. No unknown attempt is silently treated as a zero-priced complete run.
Runtime failures, summary mismatches and tool mismatches are separate counts using
the existing scorer's precedence; they are not overlapping diagnoses.

`statistical_report` reapplies comparison guards and recomputes cached aggregates,
but trusts scored case evidence just as `compare` does. It is not authentication
of a JSON report or a replacement for database reconciliation. Historical reports
remain untouched; no statistical conclusions are retroactively added to them.

See [ADR 0031](../adr/0031-exact-paired-statistics.md) and [handoff](PHASE_9A.md).

## Acceptance and scope

[Phase 9 acceptance](PHASE_9.md) independently verifies every bounded outcome-count
combination, retained arithmetic, fresh repeated CLI reports and direct database
reconciliation. It closes the scripted statistical-method gate, not a model-quality
or population-coverage claim. [Phase 9B](PHASE_9B.md) records commands, evidence and
verification limits. The prior Phase 9A handoff remains historical evidence.
