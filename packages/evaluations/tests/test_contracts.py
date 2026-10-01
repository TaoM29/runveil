"""Content identity covers every part that can affect execution or scoring."""

import pytest
from pydantic import ValidationError
from runveil_evaluations.contracts import EvalSuite, digest
from runveil_evaluations.fixtures import SUITE


def test_benchmark_identity_and_immutable_validation() -> None:
    original = digest(SUITE)
    assert digest(EvalSuite.model_validate_json(SUITE.model_dump_json())) == original
    for field, value in (
        ("task", "changed"),
        ("file_content", "changed"),
        ("expected_summary", "changed"),
        ("responses", ("changed",)),
        ("expected_tools", ("repository.read_file",)),
    ):
        changed = SUITE.cases[0].model_copy(update={field: value})
        assert digest(SUITE.model_copy(update={"cases": (changed, *SUITE.cases[1:])})) != original
    with pytest.raises(ValidationError):
        EvalSuite(name="duplicate", version="1", cases=(SUITE.cases[0], SUITE.cases[0]))
    with pytest.raises(ValidationError):
        SUITE.cases[0].task = "mutated"


def test_controlled_corpus_is_frozen_disjoint_and_read_only() -> None:
    import ast
    import json

    from runveil_evaluations.benchmark import DEVELOPMENT, HELD_OUT, select_suite

    # Released content/membership must not drift under the same benchmark version.
    assert digest(DEVELOPMENT) == "b1992916d46a1f5d7b5748069f5de387166a4a4a3aa184fae23e7d0fe997de49"
    assert digest(HELD_OUT) == "6a95d546f370e70b0b1bb128a91d66ff5f7b88ef9d2388d07a84b45465fe481f"
    cases = (*DEVELOPMENT.cases, *HELD_OUT.cases)
    assert len(DEVELOPMENT.cases) == 16 and len(HELD_OUT.cases) == 8
    assert len({case.id for case in cases}) == len({case.file_content for case in cases}) == 24
    assert len({case.task for case in cases}) == 24
    for case in cases:
        # Parsing only: no fixture module is imported, compiled for execution or called.
        ast.parse(case.file_content)
        assert len(case.file_content) < 4096
        calls = [json.loads(response) for response in case.responses[:-1]]
        assert tuple(call["tool_name"] for call in calls) == case.expected_tools
        assert calls[-1]["arguments"] == {"path": "example.py"}
        if len(calls) == 2:
            assert case.file_content.count(calls[0]["arguments"]["query"]) == 1
    assert select_suite("calibration", "development") == SUITE
    assert select_suite("code-reading", "development") == DEVELOPMENT
    assert select_suite("code-reading", "held-out") == HELD_OUT
    with pytest.raises(ValueError, match="Unsupported"):
        select_suite("calibration", "held-out")
    with pytest.raises(ValueError, match="Unsupported"):
        select_suite("code-reading", "all")
