"""Search boundaries without filesystem or subprocess access."""

import pytest
from pydantic import ValidationError
from runveil_core.sandbox_review import InspectedFile, InspectionResult
from runveil_core.sandbox_search import SearchInput, authorize_search, search_snapshot
from runveil_core.software import SEARCH_POLICY, SOFTWARE_POLICY
from runveil_core.tools import Permission, ToolError, ToolPolicy


def test_literal_bounded_search_identity_order_and_authority() -> None:
    snapshot = InspectionResult(
        files=(
            InspectedFile(path="TASK.md", content="Return\nreturn twice return\n"),
            InspectedFile(path="mean.py", content="x" * 200 + "return" + "y" * 200 + "\n.*\n"),
            InspectedFile(path="test_mean.py", content="return\n"),
        )
    )
    result = search_snapshot(snapshot, SearchInput(query="return", max_matches=2))
    assert result.inspection_digest == snapshot.digest and result.files_scanned == 3
    assert [(m.path, m.line) for m in result.matches] == [("TASK.md", 2), ("mean.py", 1)]
    assert result.truncated and result.matches[0].excerpt == "return twice return"
    assert len(result.matches[1].excerpt) == 160 and "return" in result.matches[1].excerpt
    assert search_snapshot(snapshot, SearchInput(query="absent")).matches == ()
    literal = search_snapshot(snapshot, SearchInput(query=".*"))
    assert [(m.path, m.line) for m in literal.matches] == [("mean.py", 2)]
    assert not literal.truncated
    for denied in (
        SOFTWARE_POLICY,
        ToolPolicy(allowed_tools=SEARCH_POLICY.allowed_tools, permissions=(Permission.EXECUTE,)),
    ):
        with pytest.raises(ToolError):
            authorize_search(SEARCH_POLICY, denied)
        with pytest.raises(ToolError):
            authorize_search(denied, SEARCH_POLICY)
    for query in ("", "x" * 129, "a\nb", "a\rb", "nul\0"):
        with pytest.raises(ValidationError):
            SearchInput(query=query)
    for arguments in ({"query": "x", "path": "../outside"}, {"query": "x", "max_matches": 11}):
        with pytest.raises(ValidationError):
            SearchInput.model_validate(arguments)
