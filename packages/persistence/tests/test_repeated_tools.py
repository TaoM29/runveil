"""A history-based loop guard rejects intent before dispatch, across recovery."""

import asyncio
from datetime import datetime
from uuid import UUID

import pytest
from runveil_core.agents import JsonValue
from runveil_core.models import (
    ModelRequest,
    ModelResponse,
    ProviderError,
    ProviderErrorCode,
    TokenUsage,
)
from runveil_core.runs import RunStatus
from runveil_core.runtime import (
    BudgetExceeded,
    Cursor,
    Pending,
    RuntimeConfig,
    RuntimeState,
    execute,
)
from runveil_core.tools import fixture_registry
from runveil_persistence import execution, jobs
from runveil_persistence.database import create_engine
from runveil_persistence.execution import PostgresExecutionStore, load_runtime_state
from runveil_persistence.history import HistoryRepository
from runveil_persistence.jobs import OwnershipLost, claim_next, enroll
from runveil_persistence.models import JobRow, ToolCallRow
from runveil_persistence.repositories import AgentRepository, RunRepository
from runveil_worker.worker import (
    LOOP_PROFILE,
    POLICY,
    LoopFixtureProvider,
    configuration,
    submit,
    work_once,
)
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.mark.parametrize("cut", [4, 5])
async def test_loop_guard_survives_restart_and_atomic_failure(
    database: AsyncEngine, monkeypatch: pytest.MonkeyPatch, cut: int
) -> None:
    sessions = async_sessionmaker(database)
    config = configuration(LOOP_PROFILE)
    run_id = await submit(sessions, profile=LOOP_PROFILE)
    claim = await claim_next(sessions, profile=LOOP_PROFILE, run_id=run_id)
    assert claim is not None

    class StopAfterCommit(PostgresExecutionStore):
        async def complete(
            self,
            pending: Pending,
            state: RuntimeState,
            *,
            result: dict[str, JsonValue] | None = None,
            error_code: str | None = None,
        ) -> Cursor:
            cursor = await super().complete(pending, state, result=result, error_code=error_code)
            if state.steps_used == cut:
                raise asyncio.CancelledError
            return cursor

    with pytest.raises(asyncio.CancelledError):
        await execute(
            run_id,
            claim.task,
            provider_name=config.provider,
            provider=LoopFixtureProvider(),
            store=StopAfterCommit(sessions, claim=claim, expected_config=config),
            tools=fixture_registry(),
            tool_policy=POLICY,
        )
    old = PostgresExecutionStore(sessions, claim=claim, expected_config=config)
    started = await old.start(run_id, claim.task, config.provider)
    if cut == 5:

        async def interrupt(*args: object, **kwargs: object) -> None:
            raise asyncio.CancelledError

        with monkeypatch.context() as patch:
            patch.setattr(RunRepository, "transition", interrupt)
            with pytest.raises(asyncio.CancelledError):
                await old.request(
                    started.cursor,
                    kind="tool",
                    payload={},
                    config=config,
                    tool_name="fixture.info",
                    model_invocation_id=started.state.source_model_id,
                )
        async with sessions.begin() as session:
            assert await load_runtime_state(session, run_id) == started.state
            assert (await RunRepository(session).get(run_id)).status == RunStatus.RUNNING
    async with sessions.begin() as session:
        await session.execute(
            text(
                "UPDATE worker_jobs SET expires_at=clock_timestamp() - interval '1 second' "
                "WHERE run_id=:id"
            ),
            {"id": run_id},
        )
    restarted = create_engine(database.url)
    try:
        outcome = await work_once(
            async_sessionmaker(restarted), run_id=run_id, profile=LOOP_PROFILE
        )
    finally:
        await restarted.dispose()
    assert outcome is not None
    state = outcome[1]
    assert state.error_code == "repeated_tool_limit_exceeded" and state.steps_used == 5
    assert state.tokens.attempts == 3 and state.cost is not None
    assert state.cost.known_nanousd == 75_000
    assert state.next_tool is not None and state.source_model_id is not None
    with pytest.raises(OwnershipLost):
        await old.request(
            started.cursor, kind="tool", payload={}, config=config, tool_name="fixture.info"
        )
    async with sessions.begin() as session:
        assert await load_runtime_state(session, run_id) == state
        assert (
            await session.scalar(
                select(func.count()).select_from(ToolCallRow).where(ToolCallRow.run_id == run_id)
            )
            == 2
        )
        events = await HistoryRepository(session).events(run_id)
        assert [event.kind for event in events[-2:]] == ["budget.exceeded", "run.transitioned"]
        assert events[-2].payload["budget"] == "identical_tool_calls"
    assert await work_once(sessions, run_id=run_id, profile=LOOP_PROFILE) is None


async def seed(sessions: async_sessionmaker[AsyncSession], config: RuntimeConfig) -> UUID:
    async with sessions.begin() as session:
        agents = AgentRepository(session)
        agent = await agents.create("Repeated tool boundary")
        version = await agents.create_version(agent.id, config.model_dump(mode="json"))
        run_id = (await RunRepository(session).create(version.id)).id
        await enroll(session, run_id, task="Public fixture", profile="loop-test")
        return run_id


async def test_identity_is_run_wide_structural_json_and_tool_name(database: AsyncEngine) -> None:
    sessions = async_sessionmaker(database)
    config = configuration(LOOP_PROFILE).model_copy(update={"max_identical_tool_calls": 1})
    run_id = await seed(sessions, config)
    claim = await claim_next(sessions, profile="loop-test", run_id=run_id)
    assert claim is not None
    store = PostgresExecutionStore(sessions, claim=claim, expected_config=config)
    started = await store.start(run_id, claim.task, config.provider)
    cursor, state = started.cursor, started.state
    calls: list[tuple[str, dict[str, JsonValue]]] = [
        ("fixture.a", {"a": [1, 2], "b": {"x": 1}}),
        ("fixture.b", {"a": [1, 2], "b": {"x": 1}}),
        ("fixture.a", {"a": [2, 1], "b": {"x": 1}}),
        ("fixture.a", {"a": [1, 2], "b": {"x": True}}),
    ]
    # Exercise the trusted store boundary directly; no tool handlers are dispatched.
    for name, payload in calls:
        pending = await store.request(
            cursor, kind="tool", payload=payload, config=config, tool_name=name
        )
        state = state.model_copy(update={"steps_used": state.steps_used + 1})
        cursor = await store.complete(pending, state, result={})
    with pytest.raises(BudgetExceeded) as caught:
        # Passing a relaxed configuration cannot override the immutable version.
        await store.request(
            cursor,
            kind="tool",
            payload={"b": {"x": 1.0}, "a": [1, 2]},
            config=config.model_copy(update={"max_identical_tool_calls": 64}),
            tool_name="fixture.a",
        )
    assert caught.value.state.error_code == "repeated_tool_limit_exceeded"
    assert caught.value.state.steps_used == 4


async def test_model_retry_does_not_reset_prior_tool_count(
    database: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    from runveil_core.runtime import ModelRetryPolicy

    sessions = async_sessionmaker(database)
    config = configuration(LOOP_PROFILE).model_copy(
        update={
            "max_identical_tool_calls": 1,
            "model_retry": ModelRetryPolicy(max_retries=1),
        }
    )
    run_id = await seed(sessions, config)
    claim = await claim_next(sessions, profile="loop-test", run_id=run_id)
    assert claim is not None

    class RateAfterTool(LoopFixtureProvider):
        async def generate(self, request: ModelRequest) -> ModelResponse:
            if request.messages[-1].role == "tool":
                raise ProviderError(
                    ProviderErrorCode.RATE_LIMITED,
                    usage=TokenUsage(input_tokens=0, output_tokens=0),
                )
            return await super().generate(request)

    first = await execute(
        run_id,
        claim.task,
        provider_name=config.provider,
        provider=RateAfterTool(),
        store=PostgresExecutionStore(sessions, claim=claim, expected_config=config),
        tools=fixture_registry(),
        tool_policy=POLICY,
        allow_model_retries=True,
    )
    assert first.retries_scheduled == 1 and first.steps_used == 3
    async with sessions.begin() as session:
        job = await session.get(JobRow, run_id)
        assert job is not None
        due = job.available_at

    async def now(session: AsyncSession) -> datetime:
        return due

    monkeypatch.setattr(jobs, "database_now", now)
    monkeypatch.setattr(execution, "database_now", now)
    replacement = await claim_next(sessions, profile="loop-test", run_id=run_id)
    assert replacement is not None
    state = await execute(
        run_id,
        replacement.task,
        provider_name=config.provider,
        provider=LoopFixtureProvider(),
        store=PostgresExecutionStore(sessions, claim=replacement, expected_config=config),
        tools=fixture_registry(),
        tool_policy=POLICY,
        allow_model_retries=True,
    )
    assert state.error_code == "repeated_tool_limit_exceeded" and state.steps_used == 4
    assert state.retries_scheduled == 1 and state.tokens.attempts == 3
