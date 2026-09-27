"""Single-consumer execution; storage owns transactions, core owns decisions."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Annotated, Literal, Protocol
from uuid import UUID

from pydantic import Field, model_validator

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
    ToolAction,
    validate_response,
)
from runveil_core.tools import ToolError, ToolErrorCode, ToolPolicy, ToolRegistry


class ModelRetryPolicy(Contract):
    max_retries: Annotated[int, Field(ge=0, le=3)] = 0
    base_delay_seconds: Annotated[int, Field(ge=1, le=60)] = 1

    def delay(self, retry_count: int) -> int:
        if not 1 <= retry_count <= self.max_retries:
            raise ValueError("Retry count is outside the configured limit")
        return self.base_delay_seconds * (1 << (retry_count - 1))


class RuntimeConfig(Contract):
    schema_version: Literal[2, 3, 4] = 2
    max_elapsed_seconds: Annotated[int, Field(ge=1, le=86400)] | None = None
    model_retry: ModelRetryPolicy = Field(default_factory=ModelRetryPolicy)
    tool_policy: ToolPolicy = Field(default_factory=ToolPolicy)
    provider: Name
    model: Name
    system_prompt: Annotated[str, Field(min_length=1, max_length=16384)]
    max_steps: Annotated[int, Field(ge=1, le=64)] = 8
    temperature: Annotated[float, Field(ge=0, le=2)] = 0.0
    max_output_tokens: Annotated[int, Field(gt=0, le=65536)] = 1024
    timeout_seconds: Annotated[float, Field(gt=0, le=600)] = 60.0

    @model_validator(mode="after")
    def versioned_retry_policy(self) -> RuntimeConfig:
        if self.schema_version == 2 and self.model_retry != ModelRetryPolicy():
            raise ValueError("Model retry policy requires configuration version 3")
        if (self.schema_version == 4) != (self.max_elapsed_seconds is not None):
            raise ValueError("Elapsed budget requires configuration version 4 and a limit")
        return self


class RuntimeState(Contract):
    schema_version: Literal[1, 2, 3, 4] = 2
    retries_scheduled: Annotated[int, Field(ge=0, le=3)] = 0
    retry_source_id: UUID | None = None
    messages: tuple[Message, ...]
    steps_used: Annotated[int, Field(ge=0, le=64)] = 0
    final_result: FinalResult | None = None
    error_code: str | None = None
    next_tool: ToolAction | None = None
    source_model_id: UUID | None = None


class ElapsedBudgetExceeded(Exception):
    """Storage committed an elapsed-budget terminal state before raising this."""

    def __init__(self, state: RuntimeState) -> None:
        self.state = state
        super().__init__("elapsed_time_exceeded")


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
    interrupted: Pending | None = None


@dataclass(frozen=True)
class Pending:
    cursor: Cursor
    id: UUID
    kind: Literal["model", "tool"]


class ExecutionStore(Protocol):
    async def start(self, run_id: UUID, task: str, provider: str) -> Started: ...

    async def remaining_seconds(
        self, cursor: Cursor, *, pending: Pending | None = None
    ) -> float | None: ...

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

    async def schedule_retry(
        self, pending: Pending, state: RuntimeState, *, error_code: str
    ) -> None: ...


async def execute(
    run_id: UUID,
    task: str,
    *,
    provider_name: str,
    provider: ModelProvider,
    store: ExecutionStore,
    tools: ToolRegistry | None = None,
    tool_policy: ToolPolicy | None = None,
    allow_model_retries: bool = False,
) -> RuntimeState:
    """Execute from the store's validated start/resume boundary; never replay intent."""
    try:
        return await _execute(
            run_id,
            task,
            provider_name=provider_name,
            provider=provider,
            store=store,
            tools=tools,
            tool_policy=tool_policy,
            allow_model_retries=allow_model_retries,
        )
    except ElapsedBudgetExceeded as exc:
        return exc.state


async def _execute(
    run_id: UUID,
    task: str,
    *,
    provider_name: str,
    provider: ModelProvider,
    store: ExecutionStore,
    tools: ToolRegistry | None = None,
    tool_policy: ToolPolicy | None = None,
    allow_model_retries: bool = False,
) -> RuntimeState:
    """Execute from the store's validated start/resume boundary; never replay intent."""
    registry = tools if tools is not None else ToolRegistry()
    operator_policy = tool_policy if tool_policy is not None else ToolPolicy()
    started = await store.start(run_id, task, provider_name)
    cursor, config, state = started.cursor, started.config, started.state

    async def remaining(pending: Pending | None = None) -> float | None:
        if config.max_elapsed_seconds is None:
            return None
        return await store.remaining_seconds(
            pending.cursor if pending is not None else cursor, pending=pending
        )

    await remaining(started.interrupted)
    if started.interrupted is not None:
        state = state.model_copy(
            update={"steps_used": state.steps_used + 1, "error_code": "execution_interrupted"}
        )
        await store.complete(started.interrupted, state, error_code="execution_interrupted")
        return state
    if state.retry_source_id is not None and not allow_model_retries:
        raise ValueError("Resuming model retries requires the operator retry grant")
    while True:
        await remaining()
        if state.steps_used >= config.max_steps:
            state = state.model_copy(update={"error_code": "step_limit_exceeded"})
            await store.exhaust(cursor, state)
            return state
        if state.next_tool is not None:
            action = state.next_tool
            pending = await store.request(
                cursor,
                kind="tool",
                payload=action.arguments,
                config=config,
                model_invocation_id=state.source_model_id,
                tool_name=action.tool_name,
            )
            state = state.model_copy(update={"steps_used": state.steps_used + 1})
            seconds = await remaining(pending)
            try:
                async with asyncio.timeout(seconds):
                    observation = await registry.dispatch(
                        action.tool_name, action.arguments, config.tool_policy, operator_policy
                    )
            except TimeoutError:
                await remaining(pending)
                state = state.model_copy(update={"error_code": ToolErrorCode.TIMEOUT.value})
                await store.complete(pending, state, error_code=ToolErrorCode.TIMEOUT.value)
                return state
            except ToolError as exc:
                await remaining(pending)
                state = state.model_copy(update={"error_code": exc.code.value})
                await store.complete(pending, state, error_code=exc.code.value)
                return state
            await remaining(pending)
            state = state.model_copy(
                update={
                    "messages": (
                        *state.messages,
                        Message(
                            role="tool", tool_name=action.tool_name, content=json.dumps(observation)
                        ),
                    ),
                    "next_tool": None,
                    "source_model_id": None,
                }
            )
            cursor = await store.complete(pending, state, result=observation)
            continue
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
        seconds = await remaining(pending)
        timeout = (
            min(request.timeout_seconds, seconds)
            if seconds is not None
            else request.timeout_seconds
        )
        failure: str | None = None
        retryable = False
        try:
            async with asyncio.timeout(timeout):
                response = await provider.generate(request)
            model_action = validate_response(request, response)
        except ProviderError as exc:
            failure = exc.code.value
            retryable = exc.code == ProviderErrorCode.RATE_LIMITED
        except TimeoutError:
            failure = ProviderErrorCode.TIMEOUT.value
        except Exception:
            # Only the provider/response boundary is normalized; storage errors propagate.
            failure = ProviderErrorCode.UNAVAILABLE.value
        await remaining(pending)
        if failure is not None:
            if (
                retryable
                and allow_model_retries
                and config.schema_version >= 3
                and state.retries_scheduled < config.model_retry.max_retries
                and state.steps_used < config.max_steps
            ):
                state = state.model_copy(
                    update={
                        "retries_scheduled": state.retries_scheduled + 1,
                        "retry_source_id": pending.id,
                    }
                )
                await store.schedule_retry(pending, state, error_code=failure)
                return state
            state = state.model_copy(update={"error_code": failure})
            await store.complete(pending, state, error_code=failure)
            return state
        state = state.model_copy(
            update={
                "messages": (*state.messages, Message(role="assistant", content=response.content)),
                "final_result": model_action.result
                if isinstance(model_action, FinishAction)
                else None,
                "next_tool": model_action if isinstance(model_action, ToolAction) else None,
                "source_model_id": pending.id if isinstance(model_action, ToolAction) else None,
                "retry_source_id": None,
            }
        )
        cursor = await store.complete(pending, state, result=response.model_dump(mode="json"))
        if isinstance(model_action, FinishAction):
            return state
