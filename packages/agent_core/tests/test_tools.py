import asyncio
from dataclasses import replace
from typing import Annotated

import pytest
from pydantic import Field
from runveil_core.agents import JsonValue
from runveil_core.models import Contract
from runveil_core.tools import (
    MAX_TOOL_BYTES,
    Permission,
    SideEffect,
    ToolError,
    ToolErrorCode,
    ToolPolicy,
    ToolRegistry,
    TypedTool,
)

POLICY = ToolPolicy(allowed_tools=("native.echo",), permissions=(Permission.READ,))


class Input(Contract):
    count: Annotated[int, Field(ge=1, le=3)]


class Output(Contract):
    text: str


async def echo(arguments: Input) -> Output:
    return Output(text="echo" * arguments.count)


def binding() -> TypedTool[Input, Output]:
    return TypedTool(
        name="native.echo",
        description="Echo public test data.",
        input_type=Input,
        output_type=Output,
        handler=echo,
        permission=Permission.READ,
        side_effect=SideEffect.PURE,
    )


@pytest.mark.asyncio
async def test_typed_dispatch_and_detached_schemas() -> None:
    tool = binding()
    registry = ToolRegistry([tool])
    offer = registry.offers(POLICY, POLICY)[0]
    assert offer.input_schema == Input.model_json_schema()
    assert tool.definition.output_schema == Output.model_json_schema()
    offer.input_schema.clear()
    assert registry.offers(POLICY, POLICY)[0].input_schema == Input.model_json_schema()
    assert await registry.dispatch("native.echo", {"count": 2}, POLICY, POLICY) == {
        "text": "echoecho"
    }
    with pytest.raises(ValueError, match="Duplicate"):
        ToolRegistry([tool, tool])


@pytest.mark.asyncio
@pytest.mark.parametrize("arguments", [{"count": "1"}, {"count": 0}, {"count": 1, "extra": True}])
async def test_invalid_arguments_never_reach_handler(arguments: dict[str, JsonValue]) -> None:
    calls = 0

    async def handler(arguments: Input) -> Output:
        nonlocal calls
        calls += 1
        return await echo(arguments)

    registry = ToolRegistry([replace(binding(), handler=handler)])
    with pytest.raises(ToolError) as caught:
        await registry.dispatch("native.echo", arguments, POLICY, POLICY)
    assert caught.value.code == ToolErrorCode.INVALID_ARGUMENTS and calls == 0


@pytest.mark.asyncio
async def test_authorization_is_required_at_dispatch_and_advertisement() -> None:
    calls = 0

    async def handler(arguments: Input) -> Output:
        nonlocal calls
        calls += 1
        return await echo(arguments)

    tool = replace(binding(), handler=handler)
    missing_name = ToolPolicy(permissions=(Permission.READ,))
    missing_permission = ToolPolicy(allowed_tools=("native.echo",))
    for pinned, operator in [
        (missing_name, POLICY),
        (POLICY, missing_name),
        (missing_permission, POLICY),
        (POLICY, missing_permission),
    ]:
        registry = ToolRegistry([tool])
        assert registry.offers(pinned, operator) == ()
        with pytest.raises(ToolError) as caught:
            await registry.dispatch("native.echo", {"count": 1}, pinned, operator)
        assert caught.value.code == ToolErrorCode.DENIED
    all_grants = ToolPolicy(allowed_tools=("native.echo",), permissions=tuple(Permission))
    for forbidden in [
        replace(tool, side_effect=SideEffect.MUTATING),
        replace(tool, side_effect=SideEffect.EXTERNAL),
        replace(tool, permission=Permission.WRITE),
        replace(tool, permission=Permission.EXECUTE),
        replace(tool, permission=Permission.NETWORK),
    ]:
        registry = ToolRegistry([forbidden])
        assert registry.offers(all_grants, all_grants) == ()
        with pytest.raises(ToolError) as caught:
            await registry.dispatch("native.echo", {"count": 1}, all_grants, all_grants)
        assert caught.value.code == ToolErrorCode.DENIED
    with pytest.raises(ToolError) as caught:
        await ToolRegistry().dispatch("absent", {}, POLICY, POLICY)
    assert caught.value.code == ToolErrorCode.UNAVAILABLE and calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["output", "oversize", "exception", "timeout", "cancel"])
async def test_safe_outcomes_deadline_and_cancellation(failure: str) -> None:
    calls = 0
    entered = asyncio.Event()
    stopped = asyncio.Event()

    async def handler(arguments: Input) -> Output:
        nonlocal calls
        calls += 1
        entered.set()
        try:
            if failure == "output":
                return Output.model_construct(text=123)
            if failure == "oversize":
                return Output(text="x" * MAX_TOOL_BYTES)
            if failure == "exception":
                raise RuntimeError("secret-sentinel")
            await asyncio.Event().wait()
            raise AssertionError("unreachable")
        finally:
            stopped.set()

    registry = ToolRegistry([replace(binding(), handler=handler, timeout_seconds=0.01)])
    task = asyncio.create_task(registry.dispatch("native.echo", {"count": 1}, POLICY, POLICY))
    if failure == "cancel":
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        with pytest.raises(ToolError) as caught:
            await task
        expected = {
            "output": ToolErrorCode.INVALID_OUTPUT,
            "oversize": ToolErrorCode.INVALID_OUTPUT,
            "exception": ToolErrorCode.FAILED,
            "timeout": ToolErrorCode.TIMEOUT,
        }[failure]
        assert caught.value.code == expected and "secret-sentinel" not in str(caught.value)
    assert calls == 1 and stopped.is_set()
