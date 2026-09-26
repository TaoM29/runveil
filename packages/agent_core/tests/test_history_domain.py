from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from runveil_core.history import Checkpoint, RunStep
from runveil_core.runs import RunStatus


def test_checkpoint_state_is_detached_and_unknown_schemas_fail_closed() -> None:
    checkpoint = Checkpoint(
        uuid4(),
        4,
        1,
        1,
        RunStatus.RUNNING,
        1,
        '{"messages":[{"content":"fixture"}]}',
        datetime.now(UTC),
    )
    state = checkpoint.state
    messages = state["messages"]
    assert isinstance(messages, list)
    messages.clear()
    assert checkpoint.state == {"messages": [{"content": "fixture"}]}
    with pytest.raises(ValueError, match="Unsupported checkpoint"):
        replace(checkpoint, schema_version=2)
    with pytest.raises(ValueError):
        replace(checkpoint, state_json='{"invalid":NaN}')
    with pytest.raises(ValueError, match="Step kind"):
        RunStep(checkpoint.run_id, 1, "invalid kind", "{}", checkpoint.created_at)
