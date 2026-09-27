"""Typed native tools and deny-by-default authorization for trusted async handlers."""

import asyncio
import json
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, Literal, Protocol

from pydantic import Field

from runveil_core.agents import JsonValue
from runveil_core.models import Contract, Name, ToolOffer

MAX_TOOL_BYTES = 65_536


class Permission(StrEnum):
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    NETWORK = "network"


class SideEffect(StrEnum):
    PURE = "pure"
    READ_ONLY = "read_only"
    MUTATING = "mutating"
    EXTERNAL = "external_side_effect"


class ToolPolicy(Contract):
    allowed_tools: Annotated[tuple[Name, ...], Field(max_length=128)] = ()
    permissions: tuple[Permission, ...] = ()


class ToolDefinition(Contract):
    name: Name
    description: Annotated[str, Field(min_length=1, max_length=4096)]
    input_schema: dict[str, JsonValue]
    output_schema: dict[str, JsonValue]
    permission: Permission
    side_effect: SideEffect
    timeout_seconds: Annotated[float, Field(gt=0, le=600)]
    retry_policy: Literal["never"] = "never"


class ToolErrorCode(StrEnum):
    UNAVAILABLE = "tool_unavailable"
    DENIED = "tool_permission_denied"
    INVALID_ARGUMENTS = "invalid_tool_arguments"
    INVALID_OUTPUT = "invalid_tool_output"
    TIMEOUT = "tool_timeout"
    FAILED = "tool_failed"
    RESOURCE_UNAVAILABLE = "tool_resource_unavailable"
    RESOURCE_LIMIT = "tool_resource_limit"
    RESOURCE_INVALID = "tool_resource_invalid"


class ToolError(Exception):
    def __init__(self, code: ToolErrorCode) -> None:
        self.code = ToolErrorCode(code)
        super().__init__(self.code.value)


def _bounded_json(value: dict[str, JsonValue]) -> str:
    encoded = json.dumps(value, allow_nan=False)
    if len(encoded.encode("utf-8")) > MAX_TOOL_BYTES:
        raise ValueError("Tool payload exceeds its limit")
    return encoded


@dataclass(frozen=True)
class TypedTool[Input: Contract, Output: Contract]:
    name: str
    description: str
    input_type: type[Input]
    output_type: type[Output]
    handler: Callable[[Input], Awaitable[Output]]
    permission: Permission
    side_effect: SideEffect
    timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        # Reject invalid operator metadata at registration, before any run starts.
        _ = self.definition

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            input_schema=self.input_type.model_json_schema(),
            output_schema=self.output_type.model_json_schema(),
            permission=self.permission,
            side_effect=self.side_effect,
            timeout_seconds=self.timeout_seconds,
        )

    async def invoke(self, arguments: dict[str, JsonValue]) -> dict[str, JsonValue]:
        try:
            validated = self.input_type.model_validate_json(_bounded_json(arguments), strict=True)
        except Exception:
            raise ToolError(ToolErrorCode.INVALID_ARGUMENTS) from None
        try:
            async with asyncio.timeout(self.timeout_seconds):
                output = await self.handler(validated)
        except ToolError as exc:
            # Retain only our safe enum, never handler-supplied exception text.
            raise ToolError(exc.code) from None
        except TimeoutError:
            raise ToolError(ToolErrorCode.TIMEOUT) from None
        except Exception:
            raise ToolError(ToolErrorCode.FAILED) from None
        try:
            # Revalidate even model_construct/model_copy results; no output coercion.
            if not isinstance(output, self.output_type):
                raise ValueError("Wrong output contract")
            encoded = _bounded_json(output.model_dump(mode="json", warnings="error"))
            return self.output_type.model_validate_json(encoded, strict=True).model_dump(
                mode="json"
            )
        except Exception:
            raise ToolError(ToolErrorCode.INVALID_OUTPUT) from None


class ToolBinding(Protocol):
    @property
    def definition(self) -> ToolDefinition: ...

    async def invoke(self, arguments: dict[str, JsonValue]) -> dict[str, JsonValue]: ...


class ToolRegistry:
    """No mutation/discovery API. Registration is trusted operator configuration."""

    def __init__(self, tools: Iterable[ToolBinding] = ()) -> None:
        self._tools: dict[str, ToolBinding] = {}
        for tool in tools:
            name = tool.definition.name
            if name in self._tools:
                raise ValueError("Duplicate tool name")
            self._tools[name] = tool
        if len(self._tools) > 128:
            raise ValueError("Too many tools")

    def _authorize(self, name: str, pinned: ToolPolicy, operator: ToolPolicy) -> ToolBinding:
        tool = self._tools.get(name)
        if tool is None:
            raise ToolError(ToolErrorCode.UNAVAILABLE)
        definition = tool.definition
        if (
            definition.permission != Permission.READ
            or definition.side_effect not in (SideEffect.PURE, SideEffect.READ_ONLY)
            or any(
                name not in policy.allowed_tools or definition.permission not in policy.permissions
                for policy in (pinned, operator)
            )
        ):
            raise ToolError(ToolErrorCode.DENIED)
        return tool

    def offers(self, pinned: ToolPolicy, operator: ToolPolicy) -> tuple[ToolOffer, ...]:
        offers = []
        for name in self._tools:
            try:
                definition = self._authorize(name, pinned, operator).definition
            except ToolError:
                continue
            offers.append(
                ToolOffer(
                    name=name,
                    description=definition.description,
                    input_schema=definition.input_schema,
                )
            )
        return tuple(offers)

    async def dispatch(
        self, name: str, arguments: dict[str, JsonValue], pinned: ToolPolicy, operator: ToolPolicy
    ) -> dict[str, JsonValue]:
        tool = self._authorize(name, pinned, operator)
        return await tool.invoke(arguments)


class FixtureInput(Contract):
    pass


class FixtureOutput(Contract):
    project: Literal["Runveil"] = "Runveil"
    fixture_version: Literal[1] = 1


async def _fixture_info(arguments: FixtureInput) -> FixtureOutput:
    return FixtureOutput()


def fixture_registry() -> ToolRegistry:
    return ToolRegistry(
        [
            TypedTool(
                name="fixture.info",
                description="Read fixed public metadata about the Runveil demonstration fixture.",
                input_type=FixtureInput,
                output_type=FixtureOutput,
                handler=_fixture_info,
                permission=Permission.READ,
                side_effect=SideEffect.READ_ONLY,
            )
        ]
    )
