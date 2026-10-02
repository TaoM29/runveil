"""Immutable benchmark content and selected, content-free execution evidence."""

import hashlib
import json
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator
from runveil_core.models import Contract, Name
from runveil_core.runs import RunStatus
from runveil_core.runtime import CostAccounting, RuntimeConfig, TokenAccounting

Text = Annotated[str, Field(min_length=1, max_length=4096)]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


def digest(value: Contract) -> str:
    canonical = json.dumps(value.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


class EvalCase(Contract):
    id: Name
    task: Text
    # Fixed filename avoids a fixture-writing path interpreter.
    file_content: Text
    responses: Annotated[tuple[Text, ...], Field(min_length=1, max_length=3)]
    expected_summary: Text
    expected_tools: Annotated[tuple[Name, ...], Field(max_length=2)]


class EvalSuite(Contract):
    schema_version: Literal[1] = 1
    name: Name
    version: Name
    split: Literal["development", "held-out"] = "development"
    scorer: Literal["exact-summary-and-tools-v1"] = "exact-summary-and-tools-v1"
    cases: Annotated[tuple[EvalCase, ...], Field(min_length=1, max_length=30)]

    @model_validator(mode="after")
    def unique_cases(self) -> Self:
        if len({case.id for case in self.cases}) != len(self.cases):
            raise ValueError("Duplicate case identity")
        return self


class EvalCaseResult(Contract):
    case_id: Name
    run_id: UUID
    status: RunStatus
    grade: Literal["pass", "runtime_failure", "summary_mismatch", "tool_mismatch"]
    error_code: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")] | None
    event_sequence: int
    steps: int
    model_calls: int
    tool_calls: int
    retries: int
    elapsed_ms: float
    tokens: TokenAccounting
    cost: CostAccounting


class EvalRun(Contract):
    id: UUID
    suite_digest: Digest
    implementation_digest: Digest
    agent_version_id: UUID
    agent_version_number: int
    configuration: RuntimeConfig
    started_at: AwareDatetime
    finished_at: AwareDatetime
    cases: Annotated[tuple[EvalCaseResult, ...], Field(min_length=1, max_length=30)]


class Aggregate(Contract):
    cases: int
    passed: int
    success_rate: float
    runtime_failures: int
    oracle_failures: int
    steps: int
    model_calls: int
    tool_calls: int
    retries: int
    elapsed_ms: float
    input_tokens: int
    output_tokens: int
    unknown_token_attempts: int
    known_nanousd: int
    unknown_cost_attempts: int


def aggregate(run: EvalRun) -> Aggregate:
    results = run.cases
    passed = sum(case.grade == "pass" for case in results)
    return Aggregate(
        cases=len(results),
        passed=passed,
        success_rate=passed / len(results),
        runtime_failures=sum(case.grade == "runtime_failure" for case in results),
        oracle_failures=sum(
            case.grade in ("summary_mismatch", "tool_mismatch") for case in results
        ),
        steps=sum(case.steps for case in results),
        model_calls=sum(case.model_calls for case in results),
        tool_calls=sum(case.tool_calls for case in results),
        retries=sum(case.retries for case in results),
        elapsed_ms=sum(case.elapsed_ms for case in results),
        input_tokens=sum(case.tokens.input_tokens for case in results),
        output_tokens=sum(case.tokens.output_tokens for case in results),
        unknown_token_attempts=sum(case.tokens.unknown_attempts for case in results),
        known_nanousd=sum(case.cost.known_nanousd for case in results),
        unknown_cost_attempts=sum(case.cost.unknown_attempts for case in results),
    )


class Comparison(Contract):
    schema_version: Literal[1] = 1
    scope: Literal["scripted-calibration-not-model-quality"] = (
        "scripted-calibration-not-model-quality"
    )
    accounting: Literal["synthetic-usage-and-tariff"] = "synthetic-usage-and-tariff"
    suite: EvalSuite
    baseline: EvalRun
    candidate: EvalRun
    baseline_metrics: Aggregate
    candidate_metrics: Aggregate
    success_rate_delta: float


def compare(suite: EvalSuite, baseline: EvalRun, candidate: EvalRun) -> Comparison:
    expected = tuple(case.id for case in suite.cases)
    if (
        baseline.suite_digest != digest(suite)
        or candidate.suite_digest != digest(suite)
        or baseline.implementation_digest != candidate.implementation_digest
        or tuple(case.case_id for case in baseline.cases) != expected
        or tuple(case.case_id for case in candidate.cases) != expected
    ):
        raise ValueError("Comparison requires identical benchmark, implementation and coverage")
    ids = [case.run_id for run in (baseline, candidate) for case in run.cases]
    if len(set(ids)) != len(ids) or baseline.agent_version_id == candidate.agent_version_id:
        raise ValueError("Comparison requires distinct executions and agent versions")
    left, right = aggregate(baseline), aggregate(candidate)
    return Comparison(
        suite=suite,
        baseline=baseline,
        candidate=candidate,
        baseline_metrics=left,
        candidate_metrics=right,
        success_rate_delta=right.success_rate - left.success_rate,
    )
