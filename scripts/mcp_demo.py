"""Run the public stdio MCP fixture through persisted Runveil execution."""

import asyncio
import sys
from pathlib import Path

from mcp import StdioServerParameters
from runveil_core.models import FinalResult, FinishAction, ModelResponse, ToolAction
from runveil_core.runtime import RuntimeConfig, execute
from runveil_core.scripted import ScriptedProvider
from runveil_core.tools import FixtureInput, FixtureOutput, Permission, ToolPolicy, ToolRegistry
from runveil_persistence.database import create_engine, database_url
from runveil_persistence.execution import PostgresExecutionStore, load_runtime_state
from runveil_persistence.repositories import AgentRepository, RunRepository
from runveil_tools.mcp import connect_read_tools
from runveil_worker.telemetry import telemetry
from sqlalchemy.ext.asyncio import async_sessionmaker


async def main() -> None:
    policy = ToolPolicy(allowed_tools=("mcp.fixture.info",), permissions=(Permission.READ,))
    config = RuntimeConfig(
        provider="scripted",
        model="fixture",
        system_prompt="Read only the public MCP fixture.",
        tool_policy=policy,
        max_steps=3,
    )
    server = StdioServerParameters(
        command=sys.executable,
        args=[str(Path(__file__).with_name("mcp_fixture_server.py").resolve())],
        env={},
    )
    engine = create_engine(database_url())
    try:
        sessions = async_sessionmaker(engine)
        async with connect_read_tools(server) as connection:
            binding = connection.bind(
                remote_name="info",
                name="mcp.fixture.info",
                description="Read public Runveil fixture metadata over MCP.",
                input_type=FixtureInput,
                output_type=FixtureOutput,
            )
            async with sessions.begin() as session:
                agents = AgentRepository(session)
                agent = await agents.create("Phase 11A MCP demonstration")
                version = await agents.create_version(agent.id, config.model_dump(mode="json"))
                run = await RunRepository(session).create(version.id)
            actions = (
                ToolAction(
                    action="tool_call",
                    tool_name=binding.name,
                    arguments={},
                    decision_summary="Read the selected public fixture.",
                ),
                FinishAction(
                    action="finish",
                    result=FinalResult(summary="MCP fixture verified.", artifacts=()),
                ),
            )
            provider = ScriptedProvider(
                [
                    ModelResponse(
                        model="fixture",
                        content=action.model_dump_json(),
                        finish_reason="stop",
                        latency_ms=0.0,
                    )
                    for action in actions
                ]
            )
            state = await execute(
                run.id,
                "Identify the public MCP fixture.",
                provider_name="scripted",
                provider=provider,
                store=PostgresExecutionStore(sessions),
                tools=ToolRegistry([binding]),
                tool_policy=policy,
            )
        async with sessions.begin() as session:
            assert await load_runtime_state(session, run.id) == state
            finished = await RunRepository(session).get(run.id)
        assert state.final_result is not None
        print(f"run_id={run.id} status={finished.status.value} steps={state.steps_used}")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    try:
        with telemetry():
            asyncio.run(main())
    except Exception:
        print("mcp_demo_failed", file=sys.stderr)
        raise SystemExit(1) from None
