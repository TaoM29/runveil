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
