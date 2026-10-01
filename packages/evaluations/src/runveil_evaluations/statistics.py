"""Bounded paired statistics over existing scored evidence; no execution authority."""

from collections import Counter
from math import isfinite
from statistics import mean, median
from typing import Literal

from runveil_core.models import Contract

from runveil_evaluations.contracts import Comparison, EvalRun, compare


class PairedBootstrap(Contract):
    method: Literal["exact-paired-percentile-v1"] = "exact-paired-percentile-v1"
    confidence_percent: Literal[95] = 95
    cases: int
    improved: int
    regressed: int
    unchanged: int
    delta: float
    lower: float
    upper: float
    degenerate: bool


def paired_bootstrap(baseline: tuple[bool, ...], candidate: tuple[bool, ...]) -> PairedBootstrap:
    """Exact empirical bootstrap of paired binary differences, capped at 30 pairs.

    Integer convolution counts all n**n ordered resamples without enumerating them.
    Quantiles use the smallest support point whose CDF reaches 1/40 or 39/40.
    """
    n = len(baseline)
    if (
        not 1 <= n <= 30
        or len(candidate) != n
        or any(type(value) is not bool for value in (*baseline, *candidate))
    ):
        raise ValueError("Expected 1..30 complete binary pairs")
    counts = Counter(
        int(right) - int(left) for left, right in zip(baseline, candidate, strict=True)
    )
    weights = {0: 1}
    for _ in range(n):
        following: dict[int, int] = {}
        for total, weight in weights.items():
            for difference, count in counts.items():
                value = total + difference
                following[value] = following.get(value, 0) + weight * count
        weights = following

    def quantile(numerator: int) -> float:
        cumulative = 0
        for total, weight in sorted(weights.items()):
            cumulative += weight
            if cumulative * 40 >= numerator * n**n:
                return total / n
        raise AssertionError("Incomplete bootstrap distribution")

    return PairedBootstrap(
        cases=n,
        improved=counts[1],
        regressed=counts[-1],
        unchanged=counts[0],
        delta=(counts[1] - counts[-1]) / n,
        lower=quantile(1),
        upper=quantile(39),
        degenerate=len(counts) == 1,
    )


class RunSummary(Contract):
    cases: int
    mean_elapsed_ms: float
    median_elapsed_ms: float
    mean_known_nanousd: float
    mean_total_nanousd: float | None
    unknown_cost_attempts: int
    runtime_failures: int
    summary_mismatches: int
    tool_mismatches: int


def summarize(run: EvalRun) -> RunSummary:
    elapsed = [case.elapsed_ms for case in run.cases]
    if any(not isfinite(value) or value < 0 for value in elapsed):
        raise ValueError("Elapsed time must be finite and nonnegative")
    known = mean(case.cost.known_nanousd for case in run.cases)
    unknown = sum(case.cost.unknown_attempts for case in run.cases)
    return RunSummary(
        cases=len(run.cases),
        mean_elapsed_ms=mean(elapsed),
        median_elapsed_ms=median(elapsed),
        mean_known_nanousd=float(known),
        mean_total_nanousd=float(known) if unknown == 0 else None,
        unknown_cost_attempts=unknown,
        runtime_failures=sum(case.grade == "runtime_failure" for case in run.cases),
        summary_mismatches=sum(case.grade == "summary_mismatch" for case in run.cases),
        tool_mismatches=sum(case.grade == "tool_mismatch" for case in run.cases),
    )


class StatisticalReport(Contract):
    schema_version: Literal[1] = 1
    kind: Literal["paired-statistical-calibration"] = "paired-statistical-calibration"
    interpretation: Literal["descriptive-scripted-evidence-not-model-inference"] = (
        "descriptive-scripted-evidence-not-model-inference"
    )
    comparison: Comparison
    success: PairedBootstrap
    baseline_summary: RunSummary
    candidate_summary: RunSummary


def statistical_report(comparison: Comparison) -> StatisticalReport:
    # Reapply identity/coverage guards and recompute aggregates; do not trust cached metrics.
    checked = compare(comparison.suite, comparison.baseline, comparison.candidate)
    return StatisticalReport(
        comparison=checked,
        success=paired_bootstrap(
            tuple(case.grade == "pass" for case in checked.baseline.cases),
            tuple(case.grade == "pass" for case in checked.candidate.cases),
        ),
        baseline_summary=summarize(checked.baseline),
        candidate_summary=summarize(checked.candidate),
    )
