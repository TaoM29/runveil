"""Single-consumer execution; storage owns transactions, core owns decisions."""

import asyncio
import json
from dataclasses import dataclass
from typing import Annotated, Literal, Protocol
from uuid import UUID

from pydantic import Field

from runveil_core.agents import JsonValue
from runveil_core.models import (
    Contract,
    FinalResult,
    FinishAction,
    Message,
    ModelProvider,
    ModelRequest,
    Name,
    ProviderError,
    ProviderErrorCode,
    validate_response,
)
from runveil_core.tools import ToolError, ToolPolicy, ToolRegistry


class RuntimeConfig(Contract):
    schema_version: Literal[2] = 2
    tool_policy: ToolPolicy = Field(default_factory=ToolPolicy)
    provider: Name
    model: Name
    system_prompt: Annotated[str, Field(min_length=1, max_length=16384)]
    max_steps: Annotated[int, Field(ge=1, le=64)] = 8
    temperature: Annotated[float, Field(ge=0, le=2)] = 0.0
    max_output_tokens: Annotated[int, Field(gt=0, le=65536)] = 1024
    timeout_seconds: Annotated[float, Field(gt=0, le=600)] = 60.0


class RuntimeState(Contract):
    schema_version: Literal[1] = 1
    messages: tuple[Message, ...]
    steps_used: Annotated[int, Field(ge=0, le=64)] = 0
    final_result: FinalResult | None = None
    error_code: str | None = None


@dataclass(frozen=True)
class Cursor:
    run_id: UUID
    revision: int
    sequence: int


@dataclass(frozen=True)
class Started:
    cursor: Cursor
    config: RuntimeConfig
    state: RuntimeState


@dataclass(frozen=True)
class Pending:
    cursor: Cursor
    id: UUID
    kind: Literal["model", "tool"]


class ExecutionStore(Protocol):
    async def start(self, run_id: UUID, task: str, provider: str) -> Started: ...

    async def request(
        self,
        cursor: Cursor,
        *,
        kind: Literal["model", "tool"],
        payload: dict[str, JsonValue],
        config: RuntimeConfig,
        model_invocation_id: UUID | None = None,
        tool_name: str | None = None,
    ) -> Pending: ...

    async def complete(
        self,
        pending: Pending,
        state: RuntimeState,
        *,
        result: dict[str, JsonValue] | None = None,
        error_code: str | None = None,
    ) -> Cursor: ...

    async def exhaust(self, cursor: Cursor, state: RuntimeState) -> None: ...


async def execute(
    run_id: UUID,
    task: str,
    *,
    provider_name: str,
    provider: ModelProvider,
    store: ExecutionStore,
    tools: ToolRegistry | None = None,
    tool_policy: ToolPolicy | None = None,
) -> RuntimeState:
    """Execute a new queued run once. Never retry, resume or swallow cancellation."""
    registry = tools if tools is not None else ToolRegistry()
    operator_policy = tool_policy if tool_policy is not None else ToolPolicy()
    started = await store.start(run_id, task, provider_name)
    cursor, config, state = started.cursor, started.config, started.state
    while True:
        if state.steps_used == config.max_steps:
            state = state.model_copy(update={"error_code": "step_limit_exceeded"})
            await store.exhaust(cursor, state)
            return state
        request = ModelRequest(
            model=config.model,
            messages=state.messages,
            available_tools=registry.offers(config.tool_policy, operator_policy),
            temperature=config.temperature,
            max_output_tokens=config.max_output_tokens,
            timeout_seconds=config.timeout_seconds,
        )
        pending = await store.request(
            cursor, kind="model", payload=request.model_dump(mode="json"), config=config
        )
        state = state.model_copy(update={"steps_used": state.steps_used + 1})
        failure: str | None = None
        try:
            async with asyncio.timeout(request.timeout_seconds):
                response = await provider.generate(request)
            action = validate_response(request, response)
        except ProviderError as exc:
            failure = exc.code.value
        except TimeoutError:
            failure = ProviderErrorCode.TIMEOUT.value
        except Exception:
            # Only the provider/response boundary is normalized; storage errors propagate.
            failure = ProviderErrorCode.UNAVAILABLE.value
        if failure is not None:
            state = state.model_copy(update={"error_code": failure})
            await store.complete(pending, state, error_code=failure)
            return state
        state = state.model_copy(
            update={
                "messages": (
                    *state.messages,
                    Message(role="assistant", content=response.content),
                ),
                "final_result": action.result if isinstance(action, FinishAction) else None,
            }
        )
        cursor = await store.complete(pending, state, result=response.model_dump(mode="json"))
        if isinstance(action, FinishAction):
            return state
        if state.steps_used == config.max_steps:
            state = state.model_copy(update={"error_code": "step_limit_exceeded"})
            await store.exhaust(cursor, state)
            return state
        pending = await store.request(
            cursor,
            kind="tool",
            payload=action.arguments,
            config=config,
            model_invocation_id=pending.id,
            tool_name=action.tool_name,
        )
        state = state.model_copy(update={"steps_used": state.steps_used + 1})
        try:
            observation = await registry.dispatch(
                action.tool_name, action.arguments, config.tool_policy, operator_policy
            )
        except ToolError as exc:
            state = state.model_copy(update={"error_code": exc.code.value})
            await store.complete(pending, state, error_code=exc.code.value)
            return state
        state = state.model_copy(
            update={
                "messages": (
                    *state.messages,
                    Message(
                        role="tool", tool_name=action.tool_name, content=json.dumps(observation)
                    ),
                )
            }
        )
        cursor = await store.complete(pending, state, result=observation)
