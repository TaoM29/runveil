import asyncio
import sys
from dataclasses import replace
from pathlib import Path
from uuid import UUID

import pytest
from mcp import StdioServerParameters
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from runveil_core.errors import InvalidTransition
from runveil_core.models import ModelResponse
from runveil_core.runtime import execute
from runveil_core.scripted import ScriptedProvider
from runveil_core.telemetry import using_tracer
from runveil_core.tools import FixtureInput, FixtureOutput, Permission, ToolPolicy, ToolRegistry
from runveil_persistence.execution import PostgresExecutionStore, load_runtime_state
from runveil_persistence.history import HistoryRepository
from runveil_persistence.invocations import InvocationRepository
from runveil_persistence.traces import read_trace
from runveil_tools.mcp import connect_read_tools
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from test_execution import response, seed_run

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]
SERVER = Path(__file__).resolve().parents[3] / "scripts/mcp_fixture_server.py"
POLICY = ToolPolicy(allowed_tools=("mcp.fixture.info",), permissions=(Permission.READ,))


@pytest.mark.parametrize("outcome", ["success", "error", "interrupted"])
async def test_mcp_uses_committed_intent_outcome_trace_and_no_replay(
    database: AsyncEngine, outcome: str
) -> None:
    sessions = async_sessionmaker(database)
    run_id = await seed_run(database, tool_policy=POLICY.model_dump(mode="json"))
    provider = ScriptedProvider(
        [
            ModelResponse.model_validate(
                response(tool=True).model_dump()
                | {
                    "content": response(tool=True).content.replace(
                        "fixture.info", "mcp.fixture.info"
                    )
                }
            ),
            response(),
        ]
    )
    spans = InMemorySpanExporter()
    sdk = TracerProvider(shutdown_on_exit=False)
    sdk.add_span_processor(SimpleSpanProcessor(spans))
    server = StdioServerParameters(
        command=sys.executable,
        args=[str(SERVER), "--scenario", "error" if outcome == "error" else "success"],
        env={},
    )
    try:
        async with connect_read_tools(server) as connection:
            binding = connection.bind(
                remote_name="info",
                name="mcp.fixture.info",
                description="Read public fixture metadata.",
                input_type=FixtureInput,
                output_type=FixtureOutput,
            )

            async def observed(arguments: FixtureInput) -> FixtureOutput:
                async with sessions.begin() as session:
                    await session.execute(text("SET LOCAL lock_timeout = '1s'"))
                    await session.execute(
                        text("SELECT id FROM runs WHERE id=:id FOR UPDATE"), {"id": run_id}
                    )
                    events = await HistoryRepository(session).events(run_id)
                    assert events[-1].kind == "tool.requested"
                    call = await InvocationRepository(session).get_tool(
                        run_id, UUID(str(events[-1].payload["record_id"]))
                    )
                    assert call.tool_name == binding.name and call.status.value == "REQUESTED"
                    assert call.model_invocation_id is not None
                result = await binding.handler(arguments)
                if outcome == "interrupted":
                    raise asyncio.CancelledError
                return result

            with using_tracer(sdk.get_tracer("runveil.runtime")):
                execution = execute(
                    run_id,
                    "Read the public MCP fixture.",
                    provider_name="scripted",
                    provider=provider,
                    store=PostgresExecutionStore(sessions),
                    tools=ToolRegistry([replace(binding, handler=observed)]),
                    tool_policy=POLICY,
                )
                if outcome == "interrupted":
                    with pytest.raises(asyncio.CancelledError):
                        await execution
                else:
                    state = await execution
                    assert state.error_code == ("tool_failed" if outcome == "error" else None)
                    async with sessions.begin() as session:
                        assert await load_runtime_state(session, run_id) == state
                    assert "private-sentinel" not in state.model_dump_json()

        async with sessions.begin() as session:
            trace = await read_trace(session, run_id)
            assert trace.tool_calls == 1
            assert (
                trace.status
                == {"success": "SUCCEEDED", "error": "FAILED", "interrupted": "RUNNING"}[outcome]
            )
            tool_spans = [s for s in spans.get_finished_spans() if s.name == "tool.dispatch"]
            assert len(tool_spans) == 1 and tool_spans[0].attributes is not None
            call = await InvocationRepository(session).get_tool(
                run_id, UUID(str(tool_spans[0].attributes["runveil.invocation_id"]))
            )
            assert (
                call.requested_event_sequence
                == tool_spans[0].attributes["runveil.request_sequence"]
            )
            assert (
                call.status.value
                == {"success": "SUCCEEDED", "error": "FAILED", "interrupted": "REQUESTED"}[outcome]
            )
            assert call.result == (
                {"project": "Runveil", "fixture_version": 1} if outcome == "success" else None
            )
            assert not tool_spans[0].events
        # This slice has no recoverable MCP worker profile. An uncertain call stays
        # inspectable and cannot be replayed by restarting the in-process runner.
        with pytest.raises(InvalidTransition):
            await execute(
                run_id,
                "Read again",
                provider_name="scripted",
                provider=ScriptedProvider([]),
                store=PostgresExecutionStore(sessions),
            )
    finally:
        sdk.shutdown()
