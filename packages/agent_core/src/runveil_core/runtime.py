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
    TokenUsage,
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


class ModelPricing(Contract):
    """Immutable linear tariff for a configured request binding, in nano-USD."""

    price_id: Name
    provider: Name
    model: Name
    currency: Literal["USD"] = "USD"
    input_nanousd_per_token: Annotated[int, Field(ge=0, le=1_000_000_000)]
    output_nanousd_per_token: Annotated[int, Field(ge=0, le=1_000_000_000)]


class RuntimeConfig(Contract):
    schema_version: Literal[2, 3, 4, 5, 6] = 2
    pricing: ModelPricing | None = None
    max_cost_nanousd: Annotated[int, Field(ge=1, le=1_000_000_000_000_000)] | None = None
    max_input_tokens: Annotated[int, Field(ge=1, le=1_000_000_000)] | None = None
    max_total_output_tokens: Annotated[int, Field(ge=1, le=1_000_000_000)] | None = None
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
    def versioned_budgets(self) -> RuntimeConfig:
        if self.schema_version == 2 and self.model_retry != ModelRetryPolicy():
            raise ValueError("Model retry policy requires configuration version 3")
        if (self.schema_version >= 4) != (self.max_elapsed_seconds is not None):
            raise ValueError("Elapsed budget requires configuration version 4 or later and a limit")
        if (self.schema_version >= 5) != (
            self.max_input_tokens is not None and self.max_total_output_tokens is not None
        ) or (
            self.schema_version < 5
            and (self.max_input_tokens is not None or self.max_total_output_tokens is not None)
        ):
            raise ValueError(
                "Token budgets require configuration version 5 or later and both limits"
            )
        if self.schema_version == 6:
            if self.pricing is None or self.max_cost_nanousd is None:
                raise ValueError("Cost budget requires a pinned price and a limit")
            if (self.pricing.provider, self.pricing.model) != (self.provider, self.model):
                raise ValueError("Pricing must match the configured provider/model")
        elif self.pricing is not None or self.max_cost_nanousd is not None:
            raise ValueError("Cost budget requires configuration version 6")
        return self


class TokenAccounting(Contract):
    attempts: Annotated[int, Field(ge=0, le=64)] = 0
    input_tokens: Annotated[int, Field(ge=0)] = 0
    output_tokens: Annotated[int, Field(ge=0)] = 0
    unknown_attempts: Annotated[int, Field(ge=0, le=64)] = 0
    last_usage: TokenUsage = Field(default_factory=TokenUsage)

    def add(self, usage: TokenUsage) -> TokenAccounting:
        return TokenAccounting(
            attempts=self.attempts + 1,
            input_tokens=self.input_tokens + (usage.input_tokens or 0),
            output_tokens=self.output_tokens + (usage.output_tokens or 0),
            unknown_attempts=self.unknown_attempts
            + int(usage.input_tokens is None or usage.output_tokens is None),
            last_usage=usage,
        )

    def failure(self, config: RuntimeConfig) -> str | None:
        if config.schema_version < 5:
            return None
        if self.unknown_attempts:
            return "token_usage_unknown"
        assert config.max_input_tokens is not None and config.max_total_output_tokens is not None
        if (
            self.input_tokens >= config.max_input_tokens
            or self.output_tokens >= config.max_total_output_tokens
        ):
            return "token_limit_exceeded"
        return None


class CostAccounting(Contract):
    known_nanousd: Annotated[int, Field(ge=0)] = 0
    unknown_attempts: Annotated[int, Field(ge=0, le=64)] = 0

    @classmethod
    def from_tokens(cls, tokens: TokenAccounting, pricing: ModelPricing) -> CostAccounting:
        return cls(
            known_nanousd=tokens.input_tokens * pricing.input_nanousd_per_token
            + tokens.output_tokens * pricing.output_nanousd_per_token,
            unknown_attempts=tokens.unknown_attempts,
        )


class RuntimeState(Contract):
    schema_version: Literal[1, 2, 3, 4, 5, 6] = 2
    cost: CostAccounting | None = None
    tokens: TokenAccounting = Field(default_factory=TokenAccounting)
    retries_scheduled: Annotated[int, Field(ge=0, le=3)] = 0
    retry_source_id: UUID | None = None
    messages: tuple[Message, ...]
    steps_used: Annotated[int, Field(ge=0, le=64)] = 0
    final_result: FinalResult | None = None
    error_code: str | None = None
    next_tool: ToolAction | None = None
    source_model_id: UUID | None = None

    def account_model_usage(self, usage: TokenUsage, config: RuntimeConfig) -> RuntimeState:
        tokens = self.tokens.add(usage)
        return self.model_copy(
            update={
                "tokens": tokens,
                "cost": CostAccounting.from_tokens(tokens, config.pricing)
                if config.pricing
                else None,
            }
        )

    def budget_failure(self, config: RuntimeConfig) -> str | None:
        token_failure = self.tokens.failure(config)
        if token_failure is not None:
            return token_failure
        if config.max_cost_nanousd is not None:
            assert self.cost is not None
            if self.cost.known_nanousd >= config.max_cost_nanousd:
                return "cost_limit_exceeded"
        return None


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
        if config.schema_version >= 5 and started.interrupted.kind == "model":
            state = state.account_model_usage(TokenUsage(), config)
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
        usage = TokenUsage()
        try:
            async with asyncio.timeout(timeout):
                response = await provider.generate(request)
            usage = response.usage
            model_action = validate_response(request, response)
        except ProviderError as exc:
            if usage == TokenUsage():
                usage = exc.usage
            failure = exc.code.value
            retryable = exc.code == ProviderErrorCode.RATE_LIMITED
        except TimeoutError:
            failure = ProviderErrorCode.TIMEOUT.value
        except Exception:
            # Only the provider/response boundary is normalized; storage errors propagate.
            failure = ProviderErrorCode.UNAVAILABLE.value
        if config.schema_version >= 5:
            state = state.account_model_usage(usage, config)
            budget_failure = state.budget_failure(config)
            if budget_failure is not None:
                failure, retryable = budget_failure, False
            # The outcome boundary checks elapsed time and retains this usage even
            # when it discards a late response. No content is accepted before it.
        else:
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
