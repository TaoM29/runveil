"""Small real-database evaluation acceptance and failure/authority boundary checks."""

from uuid import uuid4

import pytest
from runveil_core.models import ToolAction
from runveil_evaluations.contracts import Comparison, EvalCase, EvalSuite, compare
from runveil_evaluations.fixtures import SUITE, finish
from runveil_evaluations.runner import run_calibration, run_suite, score_case
from runveil_persistence.models import ModelInvocationRow, ToolCallRow
from runveil_persistence.repositories import AgentRepository
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_calibration_repeats_and_scores_durable_evidence(database: AsyncEngine) -> None:
    sessions = async_sessionmaker(database)
    first = await run_calibration(sessions)
    second = await run_calibration(sessions)
    assert Comparison.model_validate_json(first.model_dump_json()) == first
    for report in (first, second):
        assert report.baseline_metrics.passed == 2 and report.candidate_metrics.passed == 3
        assert report.baseline_metrics.runtime_failures == 1
        assert report.baseline_metrics.cases == report.candidate_metrics.cases == 3
        assert report.baseline_metrics.steps == 7 and report.candidate_metrics.steps == 9
        assert report.candidate_metrics.model_calls == 6
        assert report.candidate_metrics.tool_calls == 3
        assert report.candidate_metrics.input_tokens == 60
        assert report.candidate_metrics.output_tokens == 30
        assert report.candidate_metrics.known_nanousd == 120_000
        assert report.candidate_metrics.unknown_token_attempts == 0
        assert report.baseline.cases[-1].error_code == "step_limit_exceeded"
        for run in (report.baseline, report.candidate):
            async with sessions.begin() as session:
                version = await AgentRepository(session).get_version(run.agent_version_id)
                assert version.configuration == run.configuration.model_dump(mode="json")
                for case in run.cases:
                    for table, count in (
                        (ModelInvocationRow, case.model_calls),
                        (ToolCallRow, case.tool_calls),
                    ):
                        assert (
                            await session.scalar(
                                select(func.count())
                                .select_from(table)
                                .where(table.run_id == case.run_id)
                            )
                            == count
                        )
    assert first.baseline.suite_digest == second.baseline.suite_digest
    assert first.baseline.implementation_digest == second.baseline.implementation_digest
    assert [case.grade for case in first.baseline.cases] == [
        case.grade for case in second.baseline.cases
    ]
    assert first.baseline.agent_version_id != second.baseline.agent_version_id
    # Rescoring reads storage only and produces identical evidence.
    assert (
        await score_case(
            sessions,
            SUITE.cases[-1],
            first.candidate.cases[-1].run_id,
            first.candidate.agent_version_id,
        )
        == first.candidate.cases[-1]
    )
    with pytest.raises(ValueError, match="complete terminal evidence"):
        await score_case(sessions, SUITE.cases[0], first.candidate.cases[0].run_id, uuid4())
    for altered in (
        first.candidate.model_copy(update={"cases": first.candidate.cases[:-1]}),
        first.candidate.model_copy(update={"cases": tuple(reversed(first.candidate.cases))}),
        first.candidate.model_copy(update={"suite_digest": "0" * 64}),
        first.candidate.model_copy(update={"implementation_digest": "0" * 64}),
    ):
        with pytest.raises(ValueError, match="identical benchmark"):
            compare(SUITE, first.baseline, altered)
    with pytest.raises(ValueError, match="distinct executions"):
        compare(SUITE, first.candidate, first.candidate)


async def test_oracle_failures_and_untrusted_tool_requests_do_not_pass(
    database: AsyncEngine,
) -> None:
    def call(name: str, path: str) -> str:
        return ToolAction(
            action="tool_call",
            tool_name=name,
            arguments={"path": path},
            decision_summary="Attempt a fixture request.",
        ).model_dump_json()

    suite = EvalSuite(
        name="failure-calibration",
        version="1",
        cases=tuple(
            EvalCase(
                id=name,
                task="Return ok after the required read.",
                file_content="public\n",
                responses=responses,
                expected_summary="ok",
                expected_tools=("repository.read_file",),
            )
            for name, responses in (
                ("wrong-answer", (finish("wrong"),)),
                ("missing-read", (finish("ok"),)),
                ("traversal", (call("repository.read_file", "../outside"), finish("ok"))),
                ("write", (call("repository.apply_patch", "example.py"), finish("ok"))),
            )
        ),
    )
    sessions = async_sessionmaker(database)
    async with sessions.begin() as session:
        agent = await AgentRepository(session).create("Evaluation boundary fixture")
    result = await run_suite(
        sessions,
        suite,
        agent_id=agent.id,
        max_steps=5,
        implementation="0" * 64,
    )
    assert [case.grade for case in result.cases] == [
        "summary_mismatch",
        "tool_mismatch",
        "runtime_failure",
        "runtime_failure",
    ]
    assert result.cases[2].error_code == "invalid_tool_arguments"
    # Unadvertised mutation is rejected during model-response validation, before tool intent.
    assert result.cases[3].error_code == "invalid_response"
    assert result.cases[3].tool_calls == 0


async def test_controlled_benchmark_partitions_keep_complete_separate_denominators(
    database: AsyncEngine,
) -> None:
    from runveil_evaluations.benchmark import DEVELOPMENT, HELD_OUT

    sessions = async_sessionmaker(database)
    development = await run_calibration(sessions, DEVELOPMENT)
    held_out = await run_calibration(sessions, HELD_OUT)
    for report, count in ((development, 16), (held_out, 8)):
        assert report.baseline_metrics.cases == report.candidate_metrics.cases == count
        assert report.baseline_metrics.passed == count // 2
        assert report.candidate_metrics.passed == count
        assert report.baseline_metrics.runtime_failures == count // 2
        assert report.candidate_metrics.steps == count * 4
        assert report.candidate_metrics.model_calls == count * 5 // 2
        assert report.candidate_metrics.tool_calls == count * 3 // 2
        assert report.candidate_metrics.unknown_token_attempts == 0
        assert report.candidate_metrics.unknown_cost_attempts == 0
        for fixture, baseline, candidate in zip(
            report.suite.cases, report.baseline.cases, report.candidate.cases, strict=True
        ):
            assert baseline.case_id == candidate.case_id == fixture.id
            assert candidate.grade == "pass"
            assert baseline.grade == (
                "pass" if len(fixture.expected_tools) == 1 else "runtime_failure"
            )
            if baseline.grade == "runtime_failure":
                assert baseline.error_code == "step_limit_exceeded"
        assert Comparison.model_validate_json(report.model_dump_json()) == report
    with pytest.raises(ValueError, match="identical benchmark"):
        compare(DEVELOPMENT, development.baseline, held_out.candidate)
    # Partition relabeling also changes suite identity, even with unchanged cases.
    with pytest.raises(ValueError, match="identical benchmark"):
        compare(
            DEVELOPMENT.model_copy(update={"split": "held-out"}),
            development.baseline,
            development.candidate,
        )
