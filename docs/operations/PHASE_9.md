# Phase 9 acceptance and scope audit

**Acceptance complete within ADR 0031's bounded scripted statistical-method scope;
ready for closure review.** Audited 2026-10-01 at `65b14ae`. No application,
benchmark, dependency or test changes were required. This audit does not establish
model competence, inference quality, population coverage or a production regression
gate. The user authorized acceptance after the Phase 9A implementation.

## Charter-to-evidence assessment

| Requirement                           | Evidence and verdict                                                                                                                                                                                                                                                                                                        |
| ------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Paired bootstrap confidence intervals | Exact integer convolution matches an independent multinomial oracle for all 5,455 possible negative/zero/positive histograms with 1–30 pairs. Four small exhaustive ordered-resample examples also cross-check the oracle. Nominal 95% inverse-CDF percentile bounds are implemented correctly for this bounded statistic.  |
| Success rates and absolute deltas     | Complete paired denominators, candidate-minus-baseline rates, discordant/tied counts and sign are independently recomputed from case JSON. A floating-point rounding difference between subtracting rates and averaging integer differences is harmless; the audit uses a 1e-12 tolerance for derived floating values.      |
| Latency summaries                     | All-case mean and median agree with independent arithmetic. Each fresh elapsed value matches database `finished_at - started_at`, in milliseconds. This is persisted wall duration, including storage and any waiting, not provider inference latency or a controlled performance experiment.                               |
| Cost summaries                        | Means use all cases and nano-USD units. Known subtotals remain visible; any unknown cost attempt makes complete mean cost null. Synthetic examples verify no unknown attempts, unknown attempts in some cases, and unknown attempts in every case. Fresh database checkpoint accounting matches report fields.              |
| Failure categorization                | Runtime, summary and tool failures remain separate, with the existing scorer's precedence. Existing durable tests exercise all three; the audit checks each count and independently regrades all fresh reports from terminal state, final summary and ordered tool outcomes.                                                |
| Report generation and reproducibility | Fresh CLI statistical reports for calibration, development and held-out each repeat in a separate process. Grades, counts, accounting, configurations, suite identity and statistical output match; IDs, timestamps and elapsed times intentionally vary. A separate default report still uses the original Phase 8 format. |
| Methodology and synthetic acceptance  | [Methodology](STATISTICS.md), [ADR 0031](../adr/0031-exact-paired-statistics.md), the seven passing existing evaluation tests and the independent acceptance checks satisfy the scoped Phase 9 gate.                                                                                                                        |
| Provenance and pairing boundaries     | Embedded suite digests, version/configuration identity, complete ordered coverage and source/dependency fingerprints are checked. Nine incompatible comparisons are refused. CLI overwrite, symlink and invalid-split checks leave the run count and original bytes unchanged.                                              |

## Statistical-method assessment

For each observed pair, d_i = candidate pass - baseline pass. Let n_-, n_0 and n_+
be the counts of -1, 0 and +1. A paired bootstrap draws n original case indices
with replacement; the statistic for each draw is the mean of its differences.
Collapsing these differences into three counts preserves this statistic exactly.
Convolving integer counts n times therefore counts all n^n ordered draws, without
Monte Carlo error. It does not improve the empirical sample's representativeness.

The acceptance oracle used a different calculation: for every resample composition
(a, b, c), with a+b+c=n, its weight is
n!/(a!b!c!) × n_-^a × n_0^b × n_+^c at sum c-a. These weights sum to n^n. Bounds
select the first cumulative weight reaching ceil(n^n/40) and ceil(39n^n/40), then
divide by n. This independently checks the production convolution and its discrete
quantile convention, including ties, asymmetry, regressions, single cases and all
constant-outcome extremes. No stochastic tolerance or seed is needed.

The empirical resampling and percentile interpretation agree with
[MIT's bootstrap notes](https://ocw.mit.edu/courses/18-05-introduction-to-probability-and-statistics-spring-2022/mit18_05_s22_class24-prep.pdf).
Resampling common indices to preserve pairs agrees with the paired definition in
[SciPy's bootstrap documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.bootstrap.html).
Neither source certifies this implementation or the sampling design. The project's
inverse-CDF quantiles are explicit; other libraries may interpolate differently.

A nominal 95% bootstrap interval is not an exact 95% coverage guarantee. Curated,
related, public scripted cases are not independent random draws from a defined
model-task population. One run per case does not estimate within-case stochastic
variation. Constant differences collapse the empirical distribution and set
`degenerate: true`; this includes all wins and is not evidence of certainty.
No p-value, multiple-comparison adjustment, superiority or promotion verdict is
produced. Deferring McNemar, cluster bootstrap and repeated stochastic experiments
is consistent with the charter's conditional guidance and current evidence.

## Retained and fresh evidence

[Audit JSON](evidence/phase9b/audit.json) records original-artifact hashes,
independent checks, synthetic summary examples, reproducibility fingerprints,
fresh timing/cost summaries, CLI refusals and database reconciliation counts.
The Phase 8 calibration and both corpus partitions, plus Phase 9A calibration,
were parsed and independently checked. Their bytes remain unchanged. The Phase 9A
implementation fingerprint matches the current runtime and evaluator.

| Fresh report                                     | Baseline → candidate | Delta | Nominal 95% percentile bounds | Reconciled runs across two batches |
| ------------------------------------------------ | -------------------- | ----- | ----------------------------- | ---------------------------------- |
| [Calibration](evidence/phase9b/calibration.json) | 2/3 → 3/3            | +1/3  | [0, 1]                        | 12                                 |
| [Development](evidence/phase9b/development.json) | 8/16 → 16/16         | +0.5  | [0.25, 0.75]                  | 64                                 |
| [Held-out](evidence/phase9b/held-out.json)       | 4/8 → 8/8            | +0.5  | [0.125, 0.875]                | 32                                 |

Rates and bounds above are in [0, 1] units; multiply by 100 for percentage points.
These differences were deliberately constructed by three/five-step budgets.
Nonzero lower bounds in the larger partitions do not demonstrate a model gain.
The held-out runs are reproduction of public scripts, not model tuning or new
independent statistical samples. No split was pooled into a combined interval.

The two repetitions total 108 durable runs; a fresh default-format calibration
adds six, for **114 directly reconciled runs**. Each run's stored immutable
configuration, status, timestamps, event watermark, latest checkpoint, steps,
retries, token/cost accounting and invocation counts match its report. Grades were
recomputed from database fields without calling the production scorer or trace
projection. Repeat run IDs and deterministic fingerprints are retained in the
audit; only the first full report for each suite is retained.

Fresh case evidence matches Phase 9A calibration except variable identity/time
fields. It also matches Phase 8B corpus evidence after additionally excluding the
expected changed implementation fingerprint. Cost remains synthetic: candidate
mean is 40,000 nano-USD for calibration and 50,000 for each larger partition.
Failed baseline cases remain in both time/cost denominators. No latency or cost
improvement is inferred from these sequential batches.

## Boundaries, qualifications and closure

The README still described all evaluation as future work. This audit corrects that
stale summary to describe the implemented scripted harness and statistical reports,
while retaining real model-quality evaluation as future work. Historical handoffs
and the dated public-readiness review remain unchanged.

- Statistical report generation recalculates cached aggregates and applies existing
  comparison guards. It still trusts case grades and metadata. Parsing JSON is not
  authenticity checking, and hashes do not sign evidence. Historical databases are
  gone; only fresh runs were reconciled directly with storage in this audit.
- Failure grades are exclusive, ordered classifications: terminal non-success first,
  then summary mismatch, then tool mismatch. A case with both a wrong summary and
  wrong tools receives the summary category. Counts are not root-cause diagnoses.
- Unknown cost attempts suppress complete mean cost even when their known subtotal
  is zero. The audit does not assert that reported usage or pinned synthetic tariffs
  equal provider invoices. Failed or interrupted short runs can misleadingly reduce
  mean elapsed time and cost.
- Phase 9A's initial safe-error CLI abort remains unexplained. Its exception was
  not retained and this audit cannot retroactively diagnose it. All seven fresh
  CLI batches in this audit completed successfully after database readiness and
  migration were confirmed. Infrastructure exceptions still abort report creation;
  they do not become scored runtime failures.
- No execution, tool authorization, approval, observability or durability boundary
  changed. Scoped tests include existing read-only evaluation security cases.
  Full-suite and process-death evidence from Phase 9A remains historical evidence,
  not a fresh claim from this docs/evidence-only audit.

No required acceptance item remains open within ADR 0031's scripted method scope.
The original charter's broader model-quality evaluation ambitions remain future
work. Review this closure before separately authorizing a focused Phase 10 sandbox
boundary slice. No Phase 10 implementation, commit or push is authorized here.
