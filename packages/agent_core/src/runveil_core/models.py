"""Provider-neutral model contracts; no network, persistence or execution."""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Annotated, Literal, Protocol

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    TypeAdapter,
    model_validator,
)

MAX_CONTENT_LENGTH = 1_048_576
Name = Annotated[
    str, Field(min_length=1, max_length=200, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.:/-]*$")
]


class Contract(BaseModel):
    """Frozen fields with caller-owned JSON leaves; dumps detach nested data."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, allow_inf_nan=False)


class Message(Contract):
    role: Literal["system", "user", "assistant", "tool"]
    content: Annotated[str, Field(min_length=1, max_length=MAX_CONTENT_LENGTH)]
    tool_name: Name | None = None

    @model_validator(mode="after")
    def tool_identity(self) -> Message:
        if (self.role == "tool") != (self.tool_name is not None):
            raise ValueError("Only tool messages require a tool name")
        return self


class ToolOffer(Contract):
    name: Name
    description: Annotated[str, Field(min_length=1, max_length=4096)]
    input_schema: dict[str, JsonValue]


class ModelRequest(Contract):
    schema_version: Literal[1] = 1
    model: Name
    messages: Annotated[tuple[Message, ...], Field(min_length=1, max_length=256)]
    available_tools: Annotated[tuple[ToolOffer, ...], Field(max_length=128)] = ()
    temperature: Annotated[float, Field(ge=0, le=2)] = 0.0
    max_output_tokens: Annotated[int, Field(gt=0)] = 1024
    timeout_seconds: Annotated[float, Field(gt=0, le=600)] = 60.0

    @model_validator(mode="after")
    def unique_tools(self) -> ModelRequest:
        names = [tool.name for tool in self.available_tools]
        if len(names) != len(set(names)):
            raise ValueError("Tool names must be unique")
        return self


class TokenUsage(Contract):
    input_tokens: Annotated[int, Field(ge=0)] | None = None
    output_tokens: Annotated[int, Field(ge=0)] | None = None


class ModelResponse(Contract):
    schema_version: Literal[1] = 1
    model: Name
    content: Annotated[str, Field(max_length=MAX_CONTENT_LENGTH)]
    finish_reason: Literal["stop", "length", "refusal", "other"]
    usage: TokenUsage = Field(default_factory=TokenUsage)
    latency_ms: Annotated[float, Field(ge=0)]
    provider_request_id: Annotated[str, Field(min_length=1, max_length=200)] | None = None


class ToolAction(Contract):
    action: Literal["tool_call"]
    tool_name: Name
    arguments: dict[str, JsonValue]
    decision_summary: Annotated[str, Field(min_length=1, max_length=2000)]


class FinalResult(Contract):
    summary: Annotated[str, Field(min_length=1, max_length=65536)]
    artifacts: Annotated[
        tuple[Annotated[str, Field(min_length=1, max_length=2048)], ...], Field(max_length=100)
    ]


class FinishAction(Contract):
    action: Literal["finish"]
    result: FinalResult


type AgentAction = ToolAction | FinishAction
_ACTION: TypeAdapter[AgentAction] = TypeAdapter(
    Annotated[AgentAction, Field(discriminator="action")]
)


class ProviderErrorCode(StrEnum):
    TIMEOUT = "provider_timeout"
    UNAVAILABLE = "provider_unavailable"
    RATE_LIMITED = "provider_rate_limited"
    AUTHENTICATION = "provider_authentication"
    REJECTED = "provider_rejected"
    INVALID_RESPONSE = "invalid_response"
    SCRIPT_EXHAUSTED = "script_exhausted"


class ProviderError(Exception):
    """Safe code only: never wrap a provider body or raw exception message."""

    def __init__(self, code: ProviderErrorCode) -> None:
        self.code = ProviderErrorCode(code)
        super().__init__(self.code.value)


class ModelProvider(Protocol):
    async def generate(self, request: ModelRequest) -> ModelResponse: ...


def action_schema() -> dict[str, JsonValue]:
    """Return a fresh JSON Schema for the fixed structured-action envelope."""
    return _ACTION.json_schema()


def _unique_object(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError("Non-finite JSON number")


def validate_response(request: ModelRequest, response: ModelResponse) -> AgentAction:
    """Validate structure and advertised name, never authorize or execute a tool."""
    if response.finish_reason != "stop":
        raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
    try:
        # JSON mode permits arrays for immutable tuples, but never scalar coercion.
        value = json.loads(
            response.content, object_pairs_hook=_unique_object, parse_constant=_reject_constant
        )
        normalized = json.dumps(value, allow_nan=False)
        action = _ACTION.validate_json(normalized, strict=True)
    except (ValueError, RecursionError):
        raise ProviderError(ProviderErrorCode.INVALID_RESPONSE) from None
    if isinstance(action, ToolAction) and action.tool_name not in {
        tool.name for tool in request.available_tools
    }:
        raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
    return action
