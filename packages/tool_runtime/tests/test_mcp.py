import asyncio
import sys
from pathlib import Path

import pytest
from mcp import StdioServerParameters
from runveil_core.tools import (
    FixtureInput,
    FixtureOutput,
    Permission,
    ToolError,
    ToolErrorCode,
    ToolPolicy,
    ToolRegistry,
)
from runveil_tools.mcp import connect_read_tools

SERVER = Path(__file__).resolve().parents[3] / "scripts/mcp_fixture_server.py"
POLICY = ToolPolicy(allowed_tools=("mcp.fixture.info",), permissions=(Permission.READ,))


def parameters(scenario: str = "success") -> StdioServerParameters:
    return StdioServerParameters(
        command=sys.executable, args=[str(SERVER), "--scenario", scenario], env={}
    )


@pytest.mark.asyncio
async def test_stdio_tool_uses_native_validation_and_both_grants() -> None:
    async with connect_read_tools(parameters()) as connection:
        binding = connection.bind(
            remote_name="info",
            name="mcp.fixture.info",
            description="Read public fixture metadata.",
            input_type=FixtureInput,
            output_type=FixtureOutput,
        )
        registry = ToolRegistry([binding])
        assert registry.offers(POLICY, POLICY)[0].input_schema == FixtureInput.model_json_schema()
        for pinned, operator in ((POLICY, ToolPolicy()), (ToolPolicy(), POLICY)):
            assert not registry.offers(pinned, operator)
            with pytest.raises(ToolError, match="tool_permission_denied"):
                await registry.dispatch(binding.name, {}, pinned, operator)
        with pytest.raises(ToolError, match="invalid_tool_arguments"):
            await registry.dispatch(binding.name, {"command": "private-sentinel"}, POLICY, POLICY)
        assert await registry.dispatch(binding.name, {}, POLICY, POLICY) == {
            "project": "Runveil",
            "fixture_version": 1,
        }
        with pytest.raises(ToolError, match="tool_resource_invalid"):
            connection.bind(
                remote_name="info",
                name="repository.apply_patch",
                description="Cannot alias an approval capability.",
                input_type=FixtureInput,
                output_type=FixtureOutput,
            )
    with pytest.raises(ToolError, match="tool_unavailable"):
        await registry.dispatch(binding.name, {}, POLICY, POLICY)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scenario,code",
    [
        ("error", ToolErrorCode.FAILED),
        ("invalid", ToolErrorCode.FAILED),
        ("oversized", ToolErrorCode.INVALID_OUTPUT),
        ("wait", ToolErrorCode.TIMEOUT),
        ("disconnect", ToolErrorCode.FAILED),
    ],
)
async def test_remote_failures_are_safe_and_bounded(scenario: str, code: ToolErrorCode) -> None:
    async with connect_read_tools(parameters(scenario)) as connection:
        binding = connection.bind(
            remote_name="info",
            name="mcp.fixture.info",
            description="Read public fixture metadata.",
            input_type=FixtureInput,
            output_type=FixtureOutput,
            timeout_seconds=0.1 if scenario == "wait" else 5.0,
        )
        with pytest.raises(ToolError) as raised:
            await binding.invoke({})
        assert raised.value.code == code
        assert "private-sentinel" not in str(raised.value)


@pytest.mark.asyncio
async def test_schema_drift_and_cancellation() -> None:
    async with connect_read_tools(parameters("drift")) as connection:
        with pytest.raises(ToolError, match="tool_resource_invalid"):
            connection.bind(
                remote_name="info",
                name="mcp.fixture.info",
                description="Read public fixture metadata.",
                input_type=FixtureInput,
                output_type=FixtureOutput,
            )
    async with connect_read_tools(parameters("wait")) as connection:
        binding = connection.bind(
            remote_name="info",
            name="mcp.fixture.info",
            description="Read public fixture metadata.",
            input_type=FixtureInput,
            output_type=FixtureOutput,
        )
        task = asyncio.create_task(binding.invoke({}))
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", ["paginated", "malformed"])
async def test_discovery_limits_and_wire_log_redaction(
    scenario: str, caplog: pytest.LogCaptureFixture
) -> None:
    if scenario == "paginated":
        with pytest.raises(ToolError, match="tool_resource_unavailable"):
            async with connect_read_tools(parameters(scenario)):
                pytest.fail("Paginated discovery must not expose partial bindings")
    else:
        # The SDK ignores an invalid unsolicited line, then completes discovery.
        async with connect_read_tools(parameters(scenario)):
            pass
    assert "private-sentinel" not in caplog.text
