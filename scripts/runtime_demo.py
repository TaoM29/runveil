"""Offline repository search/read demo; writes a new run to DATABASE_URL."""

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory

from runveil_core.models import FinalResult, FinishAction, ModelResponse, ToolAction
from runveil_core.runtime import RuntimeConfig, execute
from runveil_core.scripted import ScriptedProvider
from runveil_core.tools import Permission, ToolPolicy, ToolRegistry
from runveil_persistence.database import create_engine, database_url
from runveil_persistence.execution import PostgresExecutionStore, load_runtime_state
from runveil_persistence.repositories import AgentRepository, RunRepository
from runveil_tools.repository import RepositoryAccess, RepositoryTools
from sqlalchemy.ext.asyncio import async_sessionmaker

POLICY = ToolPolicy(
    allowed_tools=("repository.search", "repository.read_file"), permissions=(Permission.READ,)
)


async def main() -> None:
    engine = create_engine(database_url())
    try:
        sessions = async_sessionmaker(engine)
        config = RuntimeConfig(
            tool_policy=POLICY,
            provider="scripted",
            model="fixture",
            system_prompt="Inspect only the public repository fixture.",
            max_steps=5,
        )
        async with sessions.begin() as session:
            agents = AgentRepository(session)
            agent = await agents.create("Phase 4B offline demonstration")
            version = await agents.create_version(agent.id, config.model_dump(mode="json"))
            run = await RunRepository(session).create(version.id)
        actions = (
            ToolAction(
                action="tool_call",
                tool_name="repository.search",
                arguments={"query": "Runveil"},
                decision_summary="Locate the public fixture.",
            ),
            ToolAction(
                action="tool_call",
                tool_name="repository.read_file",
                arguments={"path": "project.txt"},
                decision_summary="Read the public fixture.",
            ),
            FinishAction(
                action="finish",
                result=FinalResult(summary="Runveil repository fixture verified.", artifacts=()),
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
        with TemporaryDirectory(prefix="runveil-demo-") as temporary:
            root = Path(temporary)
            (root / "project.txt").write_text(
                "Runveil public repository fixture.\n", encoding="utf-8"
            )
            with RepositoryTools(
                root, access=RepositoryAccess(files=("project.txt",))
            ) as repository:
                state = await execute(
                    run.id,
                    "Identify this repository fixture.",
                    tools=ToolRegistry(repository.bindings()),
                    tool_policy=POLICY,
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
