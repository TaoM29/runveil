"""A fixed, versioned execution profile; no arbitrary provider/tool bindings."""

from uuid import UUID

from runveil_core.models import FinalResult, FinishAction, ModelRequest, ModelResponse, ToolAction
from runveil_core.runtime import RuntimeConfig, RuntimeState, execute
from runveil_core.tools import Permission, ToolPolicy, fixture_registry
from runveil_persistence.execution import PostgresExecutionStore
from runveil_persistence.jobs import claim_next, enroll
from runveil_persistence.repositories import AgentRepository, RunRepository
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

PROFILE = "fixture-v1"
POLICY = ToolPolicy(allowed_tools=("fixture.info",), permissions=(Permission.READ,))


def configuration() -> RuntimeConfig:
    return RuntimeConfig(
        provider="scripted-fixture-v1",
        model="fixture-v1",
        system_prompt="Identify the fixed public Runveil fixture.",
        tool_policy=POLICY,
        max_steps=3,
    )


class FixtureProvider:
    """Select a deterministic response from durable context, not process memory."""

    async def generate(self, request: ModelRequest) -> ModelResponse:
        action: ToolAction | FinishAction
        if request.messages[-1].role == "tool":
            action = FinishAction(
                action="finish",
                result=FinalResult(summary="Runveil fixture verified.", artifacts=()),
            )
        else:
            action = ToolAction(
                action="tool_call",
                tool_name="fixture.info",
                arguments={},
                decision_summary="Read the fixed public fixture.",
            )
        return ModelResponse(
            model="fixture-v1",
            content=action.model_dump_json(),
            finish_reason="stop",
            latency_ms=0.0,
        )


async def submit(sessions: async_sessionmaker[AsyncSession]) -> UUID:
    """Atomically create and enroll one new fixture run; no broker publication."""
    async with sessions.begin() as session:
        agents = AgentRepository(session)
        agent = await agents.create("Durable fixture demonstration")
        version = await agents.create_version(agent.id, configuration().model_dump(mode="json"))
        run = await RunRepository(session).create(version.id)
        await enroll(session, run.id, task="Identify the public fixture.", profile=PROFILE)
        return run.id


async def work_once(
    sessions: async_sessionmaker[AsyncSession], *, run_id: UUID | None = None
) -> tuple[UUID, RuntimeState] | None:
    claim = await claim_next(sessions, profile=PROFILE, run_id=run_id)
    if claim is None:
        return None
    state = await execute(
        claim.run_id,
        claim.task,
        provider_name=configuration().provider,
        provider=FixtureProvider(),
        tools=fixture_registry(),
        tool_policy=POLICY,
        store=PostgresExecutionStore(sessions, claim=claim, expected_config=configuration()),
    )
    return claim.run_id, state
