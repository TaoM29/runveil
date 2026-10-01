import pytest
from pydantic import ValidationError
from runveil_core.approvals import PatchProposal


def test_proposal_is_bounded_exact_review_data() -> None:
    proposal = PatchProposal(path="src/example.txt", before="old\n", after="new\n")
    assert PatchProposal.model_validate_json(proposal.model_dump_json()) == proposal
    assert proposal.digest != PatchProposal(path=proposal.path, before="old", after="new\n").digest
    for path in ("../secret", "/absolute", "a//b", "a/./b", "a\\b", "a\n", "a:stream"):
        with pytest.raises(ValidationError):
            PatchProposal(path=path, before="old", after="new")
    for before, after in (
        ("same", "same"),
        ("old", "new\x00"),
        ("old", "a" * 16385),
        ("old", "☃" * 16384),
    ):
        with pytest.raises(ValidationError):
            PatchProposal(path="example.txt", before=before, after=after)
