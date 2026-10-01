# ADR 0031: Exact paired bootstrap for bounded binary outcomes

- Status: Accepted for Phase 9A
- Date: 2026-10-01

## Decision

Add an opt-in `--statistics` report to the existing evaluator. Wrap the unchanged
Phase 8 comparison in a separately identified, versioned statistical artifact.
Keep default output and historical evidence unchanged. Re-run comparison guards
and recompute aggregates before deriving statistics. No report-import endpoint,
database schema, execution, authorization, provider or UI change is introduced.

For the existing maximum of 30 cases, compute the exact empirical distribution of
the paired bootstrap success-rate difference. Each case contributes candidate
pass minus baseline pass in {-1, 0, 1}. Draw n pairs with replacement from the n
observed pairs. Integer convolution counts the weights of every possible sum;
the total weight is n^n. Report the inverse-CDF 2.5% and 97.5% quantiles of sum/n.
This is a percentile bootstrap, not an exact-coverage confidence procedure. It is
mathematically the exhaustive paired resampling distribution, with no Monte Carlo
error, seed, dependency or configurable iteration count. The bounded binary domain
makes a small project-owned routine appropriate; no general statistics framework.

Report pair counts, delta, nominal 95% bounds and empirical degeneracy. Also report
all-case mean/median persisted elapsed milliseconds, mean known cost subtotal,
nullable mean total cost and unknown-attempt count, and separate existing failure
grades. Failed cases remain in every denominator. Cost units remain nano-USD and
synthetic, and elapsed time includes storage overhead.

## Limits and alternatives

The existing suites are public, scripted and curated, with related subjects and
only one execution per version/case. Statistical output demonstrates mechanics;
it does not establish model quality, independence, population coverage, repeated-run
variability or superiority. Every report explicitly labels this interpretation.
Constant differences produce collapsed intervals (including all wins); mark these
as degenerate, never as certainty. Small-sample discrete percentile intervals can
have poor coverage. No p-value, significance verdict or automated promotion gate.

Monte Carlo resampling would require a seed and approximation policy unnecessarily
for this bounded statistic. BCa, cluster resampling, repeated stochastic trials and
McNemar tests are deferred until a real evaluation design justifies them. The
charter says to consider McNemar where justified; current scripted evidence does
not warrant an inferential test. Latency and cost summaries are descriptive, with
no bootstrap interval or performance-regression claim.

See [methodology and usage](../operations/STATISTICS.md). Synthetic tests compare
against exhaustive resamples and check pairing, degeneracy, maximum size, invalid
coverage, failures and unknown costs. Existing database acceptance also checks the
statistical projection of freshly scored durable evidence.
