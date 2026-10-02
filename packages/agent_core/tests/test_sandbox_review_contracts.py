"""Exact inspection bounds and review rendering, including incomplete final lines."""

import pytest
from pydantic import ValidationError
from runveil_core.approvals import PatchProposal
from runveil_core.sandbox_review import InspectedFile, InspectionResult, proposal_diff


def test_inspection_requires_complete_bounded_utf8_and_diff_preserves_newlines() -> None:
    files = (
        InspectedFile(path="TASK.md", content="task"),
        InspectedFile(path="clamp.py", content="before\n"),
        InspectedFile(path="test_clamp.py", content="tests"),
    )
    result = InspectionResult(files=files)
    assert InspectionResult.model_validate_json(result.model_dump_json()).digest == result.digest
    for invalid in (
        files[:2],
        (files[0], files[0], files[2]),
        (files[0], files[1].model_copy(update={"content": "é" * 2049}), files[2]),
        (files[0], files[1].model_copy(update={"content": "nul\0"}), files[2]),
    ):
        with pytest.raises(ValidationError):
            InspectionResult(files=invalid)
    proposal = PatchProposal(path="clamp.py", before="before\n", after="after")
    assert proposal_diff(proposal) == (
        "--- a/clamp.py\n+++ b/clamp.py\n@@ -1 +1 @@\n-before\n+after\n"
        "\\ No newline at end of file\n"
    )
