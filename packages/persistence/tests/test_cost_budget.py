"""Cost thresholds reject actions, while partial usage preserves a lower bound."""

import pytest
from runveil_core.models import ModelRequest, ModelResponse, TokenUsage
from runveil_core.runs import RunStatus
from runveil_core.runtime import execute
from runveil_core.tools import fixture_registry
from runveil_persistence.execution import PostgresExecutionStore, load_runtime_state
from runveil_persistence.history import HistoryRepository
from runveil_persistence.jobs import claim_next, enroll
from runveil_persistence.models import ModelInvocationRow, ToolCallRow
from runveil_persistence.repositories import AgentRepository, RunRepository
from runveil_worker.worker import COST_PROFILE, POLICY, FixtureProvider, configuration
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.mark.parametrize(
    "limit,partial,attempts,tool_calls",
    [
        (25_000, False, 1, 0),
        (49_999, False, 2, 1),
        (50_000, False, 2, 1),
        (100_000, True, 1, 0),
    ],
)
async def test_cost_threshold_and_unknown_usage(
    database: AsyncEngine, limit: int, partial: bool, attempts: int, tool_calls: int
) -> None:
    sessions = async_sessionmaker(database)
    config = configuration(COST_PROFILE).model_copy(update={"max_cost_nanousd": limit})
    async with sessions.begin() as session:
        agents = AgentRepository(session)
        agent = await agents.create("Synthetic cost boundary")
        version = await agents.create_version(agent.id, config.model_dump(mode="json"))
        run_id = (await RunRepository(session).create(version.id)).id
        await enroll(session, run_id, task="Public fixture", profile="cost-test")
    claim = await claim_next(sessions, profile="cost-test", run_id=run_id)
    assert claim is not None

    class Provider(FixtureProvider):
        async def generate(self, request: ModelRequest) -> ModelResponse:
            return (await super().generate(request)).model_copy(
                update={
                    "usage": TokenUsage(input_tokens=10, output_tokens=None if partial else 5),
                }
            )

    state = await execute(
        run_id,
        claim.task,
        provider_name=config.provider,
        provider=Provider(),
        store=PostgresExecutionStore(sessions, claim=claim, expected_config=config),
        tools=fixture_registry(),
        tool_policy=POLICY,
        allow_model_retries=True,
    )
    assert state.error_code == ("token_usage_unknown" if partial else "cost_limit_exceeded")
    assert state.final_result is None and state.next_tool is None
    assert state.tokens.attempts == attempts and state.retries_scheduled == 0
    assert state.cost is not None
    assert state.cost.known_nanousd == (12_500 if partial else 25_000 * attempts)
    assert state.cost.unknown_attempts == int(partial)
    async with sessions.begin() as session:
        assert await load_runtime_state(session, run_id) == state
        assert (await RunRepository(session).get(run_id)).status == RunStatus.FAILED
        assert (
            await session.scalar(
                select(func.count()).select_from(ToolCallRow).where(ToolCallRow.run_id == run_id)
            )
            == tool_calls
        )
        last = await session.scalar(
            select(ModelInvocationRow)
            .where(ModelInvocationRow.run_id == run_id)
            .order_by(ModelInvocationRow.requested_event_sequence.desc())
            .limit(1)
        )
        assert last is not None and last.result is None and last.error_code == state.error_code
        events = await HistoryRepository(session).events(run_id)
        assert events[-2].payload == {
            "budget": "tokens" if partial else "cost",
            "error_code": state.error_code,
        }
        assert events[-1].kind == "run.transitioned"
