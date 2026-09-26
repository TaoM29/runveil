from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from runveil_core.invocations import InvocationStatus, ModelInvocation, validate_outcome


def test_snapshots_detach_json_and_reject_inconsistent_outcomes() -> None:
    requested = ModelInvocation(
        id=uuid4(),
        run_id=uuid4(),
        status=InvocationStatus.REQUESTED,
        requested_event_sequence=3,
        completed_event_sequence=None,
        step_number=None,
        request_json='{"messages":[{"content":"fixture"}]}',
        result_json=None,
        error_code=None,
        requested_at=datetime.now(UTC),
        completed_at=None,
        provider="fixture",
        model="scripted",
    )
    copied = requested.request["messages"]
    assert isinstance(copied, list)
    copied.clear()
    assert requested.request == {"messages": [{"content": "fixture"}]}
    completed = replace(
        requested,
        status=InvocationStatus.SUCCEEDED,
        completed_event_sequence=4,
        step_number=1,
        result_json='{"content":["fixture"]}',
        completed_at=datetime.now(UTC),
    )
    result = completed.result
    assert result is not None
    result["content"] = []
    assert completed.result == {"content": ["fixture"]}
    with pytest.raises(ValueError):
        replace(completed, status=InvocationStatus.FAILED)
    with pytest.raises(ValueError):
        replace(completed, status=InvocationStatus.FAILED, result_json="null", error_code="failure")
    with pytest.raises(ValueError):
        replace(requested, result_json="{}")
    with pytest.raises(ValueError):
        replace(requested, request_json='{"invalid":NaN}')
    with pytest.raises(ValueError, match="Error code"):
        validate_outcome(None, "Raw exception details should not be stored here")
