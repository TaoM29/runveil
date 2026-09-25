from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from runveil_core.agents import AgentDefinition, AgentVersion, JsonValue, configuration_json
from runveil_core.errors import InvalidTransition
from runveil_core.runs import Run, RunStatus

ALLOWED = {
    "QUEUED": {"RUNNING", "CANCELLED"},
    "RUNNING": {"WAITING_FOR_APPROVAL", "RETRYING", "SUCCEEDED", "FAILED", "CANCELLED"},
    "WAITING_FOR_APPROVAL": {"RUNNING", "FAILED", "CANCELLED"},
    "RETRYING": {"RUNNING", "FAILED", "CANCELLED"},
    "SUCCEEDED": set(),
    "FAILED": set(),
    "CANCELLED": set(),
}
NOW = datetime(2026, 9, 25, tzinfo=UTC)


@pytest.mark.parametrize("source", list(RunStatus))
@pytest.mark.parametrize("target", list(RunStatus))
def test_transition_matrix(source: RunStatus, target: RunStatus) -> None:
    run = Run(uuid4(), uuid4(), source, 0, NOW, NOW)
    if target.value in ALLOWED[source.value]:
        updated = run.transition(target, at=NOW + timedelta(seconds=1))
        assert updated.status == target
        assert updated.revision == 1
        assert run.status == source
    else:
        with pytest.raises(InvalidTransition):
            run.transition(target, at=NOW + timedelta(seconds=1))


def test_lifecycle_preserves_first_start_and_records_terminal_time() -> None:
    queued = Run(uuid4(), uuid4(), RunStatus.QUEUED, 0, NOW, NOW)
    started = queued.transition(RunStatus.RUNNING, at=NOW + timedelta(seconds=1))
    waiting = started.transition(RunStatus.WAITING_FOR_APPROVAL, at=NOW + timedelta(seconds=2))
    resumed = waiting.transition(RunStatus.RUNNING, at=NOW + timedelta(seconds=3))
    finished = resumed.transition(RunStatus.SUCCEEDED, at=NOW + timedelta(seconds=4))
    assert finished.started_at == started.started_at
    assert finished.finished_at == finished.state_changed_at == NOW + timedelta(seconds=4)
    assert finished.revision == 4
    assert waiting.finished_at is None


def test_cancel_before_start() -> None:
    queued = Run(uuid4(), uuid4(), RunStatus.QUEUED, 0, NOW, NOW)
    cancelled = queued.transition(RunStatus.CANCELLED, at=NOW)
    assert cancelled.started_at is None
    assert cancelled.finished_at == NOW


@pytest.mark.parametrize("at", [NOW - timedelta(seconds=1), NOW.replace(tzinfo=None)])
def test_invalid_transition_time(at: datetime) -> None:
    with pytest.raises(ValueError, match="time"):
        Run(uuid4(), uuid4(), RunStatus.QUEUED, 0, NOW, NOW).transition(RunStatus.RUNNING, at=at)


def test_version_configuration_is_deeply_detached_and_frozen() -> None:
    values: list[JsonValue] = [1]
    source: dict[str, JsonValue] = {"nested": {"values": values}}
    version = AgentVersion(uuid4(), uuid4(), 1, configuration_json(source), NOW)
    values.append(2)
    decoded = version.configuration
    decoded["nested"] = None
    assert version.configuration == {"nested": {"values": [1]}}
    with pytest.raises(FrozenInstanceError):
        version.number = 2  # type: ignore[misc]  # Deliberately exercise frozen runtime protection.


@pytest.mark.parametrize("value", ["[]", "null", '{"x":NaN}', '{"x":Infinity}'])
def test_invalid_configuration(value: str) -> None:
    with pytest.raises(ValueError):
        AgentVersion(uuid4(), uuid4(), 1, value, NOW)


@pytest.mark.parametrize("name", ["", " ", "a" * 201])
def test_invalid_agent_name(name: str) -> None:
    with pytest.raises(ValueError):
        AgentDefinition(uuid4(), name, NOW)
