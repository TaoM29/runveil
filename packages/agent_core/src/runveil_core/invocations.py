"""Persisted intent and outcomes, independent of provider/tool execution."""

import json
import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import cast
from uuid import UUID

from runveil_core.agents import JsonValue, configuration_json


class InvocationStatus(StrEnum):
    REQUESTED = "REQUESTED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


def validate_label(value: str) -> None:
    if not value.strip() or len(value) > 200 or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError("Record labels must contain 1–200 printable characters")


def validate_outcome(result: dict[str, JsonValue] | None, error_code: str | None) -> None:
    if (result is None) == (error_code is None):
        raise ValueError("Supply exactly one result object or error code")
    if result is not None:
        configuration_json(result)
    if error_code is not None and re.fullmatch(r"[a-z][a-z0-9_]{0,63}", error_code) is None:
        raise ValueError("Error code must be a lowercase identifier of 1–64 characters")


@dataclass(frozen=True, kw_only=True)
class _InvocationRecord:
    id: UUID
    run_id: UUID
    status: InvocationStatus
    requested_event_sequence: int
    completed_event_sequence: int | None
    step_number: int | None
    request_json: str
    result_json: str | None
    error_code: str | None
    requested_at: datetime
    completed_at: datetime | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "request_json", configuration_json(json.loads(self.request_json)))
        if self.requested_event_sequence < 1 or self.requested_at.utcoffset() is None:
            raise ValueError("Invalid request position or timestamp")
        if self.status == InvocationStatus.REQUESTED:
            if any(
                value is not None
                for value in (
                    self.completed_event_sequence,
                    self.step_number,
                    self.result_json,
                    self.error_code,
                    self.completed_at,
                )
            ):
                raise ValueError("Requested records cannot contain an outcome")
        else:
            if self.status not in (InvocationStatus.SUCCEEDED, InvocationStatus.FAILED):
                raise ValueError("Invalid invocation status")
            if (
                self.completed_event_sequence is None
                or self.completed_event_sequence <= self.requested_event_sequence
                or self.step_number is None
                or self.step_number < 1
                or self.completed_at is None
                or self.completed_at.utcoffset() is None
                or self.completed_at < self.requested_at
            ):
                raise ValueError("Invalid completion boundary")
            result = None if self.result_json is None else json.loads(self.result_json)
            if self.result_json is not None:
                configuration_json(json.loads(self.result_json))
            validate_outcome(result, self.error_code)
            if (self.status == InvocationStatus.SUCCEEDED) != (result is not None):
                raise ValueError("Outcome does not match status")
            if result is not None:
                object.__setattr__(self, "result_json", configuration_json(result))

    @property
    def request(self) -> dict[str, JsonValue]:
        return cast(dict[str, JsonValue], json.loads(self.request_json))

    @property
    def result(self) -> dict[str, JsonValue] | None:
        return (
            None
            if self.result_json is None
            else cast(dict[str, JsonValue], json.loads(self.result_json))
        )


@dataclass(frozen=True, kw_only=True)
class ModelInvocation(_InvocationRecord):
    provider: str
    model: str

    def __post_init__(self) -> None:
        super().__post_init__()
        validate_label(self.provider)
        validate_label(self.model)


@dataclass(frozen=True, kw_only=True)
class ToolCall(_InvocationRecord):
    tool_name: str
    model_invocation_id: UUID | None

    def __post_init__(self) -> None:
        super().__post_init__()
        validate_label(self.tool_name)

    @property
    def arguments(self) -> dict[str, JsonValue]:
        return self.request
