"""Agent identity and immutable configuration snapshots."""

import json
from dataclasses import dataclass
from datetime import datetime
from typing import cast
from uuid import UUID

type JsonValue = None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]


def configuration_json(configuration: dict[str, JsonValue]) -> str:
    """Detach and normalize JSON; reject non-finite numbers and non-JSON values."""
    if not isinstance(configuration, dict):
        raise ValueError("Agent configuration must be a JSON object")
    return json.dumps(configuration, sort_keys=True, separators=(",", ":"), allow_nan=False)


@dataclass(frozen=True)
class AgentDefinition:
    id: UUID
    name: str
    created_at: datetime

    def __post_init__(self) -> None:
        if not self.name.strip() or len(self.name) > 200:
            raise ValueError("Agent name must contain 1–200 characters and not be blank")


@dataclass(frozen=True)
class AgentVersion:
    id: UUID
    agent_id: UUID
    number: int
    configuration_json: str
    created_at: datetime

    def __post_init__(self) -> None:
        if self.number < 1:
            raise ValueError("Version number must be positive")
        # Validate even snapshots constructed directly by callers.
        value = json.loads(self.configuration_json)
        object.__setattr__(self, "configuration_json", configuration_json(value))

    @property
    def configuration(self) -> dict[str, JsonValue]:
        """Return a new copy, including nested values, on every access."""
        return cast(dict[str, JsonValue], json.loads(self.configuration_json))
