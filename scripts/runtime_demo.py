"""Offline model → fixture tool → model demo; writes a new run to DATABASE_URL."""

import asyncio

from runveil_core.models import FinalResult, FinishAction, ModelResponse, ToolAction
from runveil_core.runtime import RuntimeConfig, execute
from runveil_core.scripted import ScriptedProvider
from runveil_core.tools import Permission, ToolPolicy, fixture_registry
from runveil_persistence.database import create_engine, database_url
from runveil_persistence.execution import PostgresExecutionStore, load_runtime_state
from runveil_persistence.repositories import AgentRepository, RunRepository
from sqlalchemy.ext.asyncio import async_sessionmaker

FIXTURE_POLICY = ToolPolicy(allowed_tools=("fixture.info",), permissions=(Permission.READ,))


async def main() -> None:
    engine = create_engine(database_url())
    try:
        sessions = async_sessionmaker(engine)
        config = RuntimeConfig(
            tool_policy=FIXTURE_POLICY,
            provider="scripted",
            model="fixture",
            system_prompt="Inspect the public fixture.",
            max_steps=3,
        )
        async with sessions.begin() as session:
            agents = AgentRepository(session)
            agent = await agents.create("Phase 4A offline demonstration")
            version = await agents.create_version(agent.id, config.model_dump(mode="json"))
            run = await RunRepository(session).create(version.id)
        actions = (
            ToolAction(
                action="tool_call",
                tool_name="fixture.info",
                arguments={},
                decision_summary="Read public fixture metadata.",
            ),
            FinishAction(
                action="finish",
                result=FinalResult(summary="Runveil fixture version 1 verified.", artifacts=()),
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
            "Identify this fixture.",
            tools=fixture_registry(),
            tool_policy=FIXTURE_POLICY,
            provider_name="scripted",
            provider=provider,
            store=PostgresExecutionStore(sessions),
        )
        async with sessions.begin() as session:
            restored = await load_runtime_state(session, run.id)
            finished = await RunRepository(session).get(run.id)
        assert restored == state and restored.final_result is not None
        print(f"run_id={run.id} status={finished.status.value} steps={restored.steps_used}")
        print(restored.final_result.summary)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
