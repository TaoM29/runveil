"""Synthetic method oracles and report boundaries, independent of paid providers."""

from itertools import product
from pathlib import Path

import pytest
from runveil_evaluations.contracts import Comparison
from runveil_evaluations.statistics import StatisticalReport, paired_bootstrap, statistical_report


def test_exact_bootstrap_matches_exhaustive_paired_resampling() -> None:
    # Includes ties, both discordance directions, and an asymmetric empirical sample.
    for differences in ((0,), (1, 1), (-1, -1), (-1, 0, 1), (0, 1, 1, -1, 0)):
        baseline = tuple(value == -1 for value in differences)
        candidate = tuple(value == 1 for value in differences)
        actual = paired_bootstrap(baseline, candidate)
        n = len(differences)
        ordered = sorted(sum(sample) / n for sample in product(differences, repeat=n))
        assert actual.lower == ordered[(len(ordered) + 39) // 40 - 1]
        assert actual.upper == ordered[(39 * len(ordered) + 39) // 40 - 1]
        assert actual.delta == sum(differences) / n
        assert actual.degenerate == (len(set(differences)) == 1)
        assert actual.improved + actual.regressed + actual.unchanged == n
    # Pairing matters even when both marginal success rates are identical.
    assert paired_bootstrap((False, True), (False, True)).lower == 0
    assert paired_bootstrap((False, True), (True, False)).lower == -1
    maximum = paired_bootstrap((False,) * 30, (True,) * 15 + (False,) * 15)
    assert maximum.lower == pytest.approx(10 / 30)
    assert maximum.upper == pytest.approx(20 / 30)
    for left, right in (((), ()), ((True,), ()), ((True,) * 31, (True,) * 31)):
        with pytest.raises(ValueError, match="binary pairs"):
            paired_bootstrap(left, right)


def test_report_rechecks_pairing_and_preserves_unknown_costs() -> None:
    root = Path(__file__).resolve().parents[3]
    comparison = Comparison.model_validate_json(
        (root / "docs/operations/evidence/phase8/calibration.json").read_text()
    )
    cases = comparison.baseline.cases
    modified = tuple(
        case.model_copy(
            update={
                "elapsed_ms": float(index * 10),
                "grade": grade,
                "cost": case.cost.model_copy(update={"known_nanousd": 100, "unknown_attempts": 1}),
            }
        )
        for index, (case, grade) in enumerate(
            zip(cases, ("runtime_failure", "summary_mismatch", "tool_mismatch"), strict=True)
        )
    )
    comparison = comparison.model_copy(
        update={"baseline": comparison.baseline.model_copy(update={"cases": modified})}
    )
    report = statistical_report(comparison)
    assert StatisticalReport.model_validate_json(report.model_dump_json()) == report
    assert report.comparison.baseline_metrics.passed == 0  # Recomputed, not stale cached 2/3.
    summary = report.baseline_summary
    assert summary.mean_elapsed_ms == summary.median_elapsed_ms == 10
    assert summary.mean_known_nanousd == 100 and summary.mean_total_nanousd is None
    assert summary.unknown_cost_attempts == 3
    assert summary.runtime_failures == summary.summary_mismatches == summary.tool_mismatches == 1
    assert report.candidate_summary.mean_total_nanousd is not None
    for update in (
        {"suite_digest": "0" * 64},
        {"implementation_digest": "0" * 64},
        {"cases": tuple(reversed(comparison.candidate.cases))},
        {"cases": comparison.candidate.cases[:-1]},
        {"agent_version_id": comparison.baseline.agent_version_id},
        {"cases": modified},
    ):
        with pytest.raises(ValueError):
            statistical_report(
                comparison.model_copy(
                    update={"candidate": comparison.candidate.model_copy(update=update)}
                )
            )
