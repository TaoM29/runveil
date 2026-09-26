"""Immutable execution history and opaque, versioned checkpoint state."""

import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import cast
from uuid import UUID

from runveil_core.agents import JsonValue, configuration_json
from runveil_core.runs import RunStatus


def validate_step_kind(kind: str) -> None:
    if re.fullmatch(r"[a-z][a-z0-9_.]{0,99}", kind) is None:
        raise ValueError("Step kind must be a lowercase identifier of 1–100 characters")


@dataclass(frozen=True)
class RunStep:
    """A recorded execution boundary, not a scheduled unit of work."""

    run_id: UUID
    number: int
    kind: str
    details_json: str
    created_at: datetime

    def __post_init__(self) -> None:
        validate_step_kind(self.kind)
        if self.number < 1:
            raise ValueError("Step number must be positive")
        object.__setattr__(self, "details_json", configuration_json(json.loads(self.details_json)))

    @property
    def details(self) -> dict[str, JsonValue]:
        return cast(dict[str, JsonValue], json.loads(self.details_json))


@dataclass(frozen=True)
class ExecutionEvent:
    run_id: UUID
    sequence: int
    kind: str
    run_revision: int
    step_number: int | None
    payload_json: str
    created_at: datetime

    def __post_init__(self) -> None:
        if self.sequence < 1 or self.run_revision < 0:
            raise ValueError("Invalid event position")
        object.__setattr__(self, "payload_json", configuration_json(json.loads(self.payload_json)))

    @property
    def payload(self) -> dict[str, JsonValue]:
        return cast(dict[str, JsonValue], json.loads(self.payload_json))


@dataclass(frozen=True)
class Checkpoint:
    """Full caller state at an event watermark; this does not resume execution."""

    run_id: UUID
    event_sequence: int
    step_number: int
    run_revision: int
    run_status: RunStatus
    schema_version: int
    state_json: str
    created_at: datetime

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("Unsupported checkpoint schema version")
        if self.event_sequence < 1 or self.step_number < 1 or self.run_revision < 0:
            raise ValueError("Invalid checkpoint position")
        object.__setattr__(self, "state_json", configuration_json(json.loads(self.state_json)))

    @property
    def state(self) -> dict[str, JsonValue]:
        return cast(dict[str, JsonValue], json.loads(self.state_json))
