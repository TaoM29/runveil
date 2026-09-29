"""Independent intent budgets, including retries and uncertain recovery."""

import asyncio
from datetime import datetime
from typing import Literal
from uuid import UUID

import pytest
from runveil_core.agents import JsonValue
from runveil_core.models import ModelRequest, ModelResponse
from runveil_core.runs import RunStatus
from runveil_core.runtime import (
    Cursor,
    ModelRetryPolicy,
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
from runveil_persistence.models import JobRow, ModelInvocationRow, ToolCallRow
from runveil_persistence.repositories import AgentRepository, RunRepository
from runveil_worker.worker import (
    CALLS_PROFILE,
    POLICY,
    LoopFixtureProvider,
    TokenFixtureProvider,
    configuration,
)
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def seed(sessions: async_sessionmaker[AsyncSession], config: RuntimeConfig) -> UUID:
    async with sessions.begin() as session:
        agents = AgentRepository(session)
        agent = await agents.create("Call limit boundary")
        version = await agents.create_version(agent.id, config.model_dump(mode="json"))
        run_id = (await RunRepository(session).create(version.id)).id
        await enroll(session, run_id, task="Public fixture", profile="calls-test")
        return run_id


async def expire(sessions: async_sessionmaker[AsyncSession], run_id: UUID) -> None:
    async with sessions.begin() as session:
        await session.execute(
            text(
                "UPDATE worker_jobs SET expires_at=clock_timestamp() "
                "- interval '1 second' WHERE run_id=:id"
            ),
            {"id": run_id},
        )


@pytest.mark.parametrize(
    "model,tool,error,steps",
    [
        (0, 1, "model_call_limit_exceeded", 0),
        (2, 0, "tool_call_limit_exceeded", 1),
        (2, 1, None, 3),
    ],
)
async def test_zero_caps_and_finish_at_exact_limits(
    database: AsyncEngine, model: int, tool: int, error: str | None, steps: int
) -> None:
    sessions = async_sessionmaker(database)
    config = configuration(CALLS_PROFILE).model_copy(
        update={"max_model_calls": model, "max_tool_calls": tool}
    )
    run_id = await seed(sessions, config)
    claim = await claim_next(sessions, profile="calls-test", run_id=run_id)
    assert claim is not None
    state = await execute(
        run_id,
        claim.task,
        provider_name=config.provider,
        provider=TokenFixtureProvider(2),
        store=PostgresExecutionStore(sessions, claim=claim, expected_config=config),
        tools=fixture_registry(),
        tool_policy=POLICY,
    )
    assert state.error_code == error and state.steps_used == steps
    assert (state.final_result is not None) == (error is None)
    async with sessions.begin() as session:
        assert await load_runtime_state(session, run_id) == state
        models = await session.scalar(
            select(func.count())
            .select_from(ModelInvocationRow)
            .where(ModelInvocationRow.run_id == run_id)
        )
        tools = await session.scalar(
            select(func.count()).select_from(ToolCallRow).where(ToolCallRow.run_id == run_id)
        )
        assert (models, tools) == ((0, 0) if model == 0 else ((1, 0) if tool == 0 else (2, 1)))
        events = await HistoryRepository(session).events(run_id)
        if error:
            assert events[-2].payload == {
                "budget": "model_calls" if model == 0 else "tool_calls",
                "error_code": error,
            }
    assert await claim_next(sessions, profile="calls-test", run_id=run_id) is None


@pytest.mark.parametrize("kind,cut", [("model", 2), ("tool", 3)])
async def test_admission_survives_restart_rollback_and_stale_owner(
    database: AsyncEngine, monkeypatch: pytest.MonkeyPatch, kind: Literal["model", "tool"], cut: int
) -> None:
    sessions = async_sessionmaker(database)
    config = configuration(CALLS_PROFILE).model_copy(
        update={"max_model_calls": 1 if kind == "model" else 3}
    )
    run_id = await seed(sessions, config)
    claim = await claim_next(sessions, profile="calls-test", run_id=run_id)
    assert claim is not None

    class Stop(PostgresExecutionStore):
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
            store=Stop(sessions, claim=claim, expected_config=config),
            tools=fixture_registry(),
            tool_policy=POLICY,
        )
    old = PostgresExecutionStore(sessions, claim=claim, expected_config=config)
    started = await old.start(run_id, claim.task, config.provider)

    async def interrupt(*args: object, **kwargs: object) -> None:
        raise asyncio.CancelledError

    with monkeypatch.context() as patch:
        patch.setattr(RunRepository, "transition", interrupt)
        with pytest.raises(asyncio.CancelledError):
            await old.request(
                started.cursor,
                kind=kind,
                payload={},
                tool_name="fixture.info" if kind == "tool" else None,
                config=config.model_copy(update={"max_model_calls": 64, "max_tool_calls": 64}),
            )
    async with sessions.begin() as session:
        assert await load_runtime_state(session, run_id) == started.state
        assert (await RunRepository(session).get(run_id)).status == RunStatus.RUNNING
    await expire(sessions, run_id)
    restarted = create_engine(database.url)
    calls: list[ModelRequest] = []

    class Provider(LoopFixtureProvider):
        async def generate(self, request: ModelRequest) -> ModelResponse:
            calls.append(request)
            return await super().generate(request)

    try:
        fresh = async_sessionmaker(restarted)
        replacement = await claim_next(fresh, profile="calls-test", run_id=run_id)
        assert replacement is not None
        state = await execute(
            run_id,
            replacement.task,
            provider_name=config.provider,
            provider=Provider(),
            store=PostgresExecutionStore(fresh, claim=replacement, expected_config=config),
            tools=fixture_registry(),
            tool_policy=POLICY,
        )
    finally:
        await restarted.dispose()
    assert not calls and state.error_code == f"{kind}_call_limit_exceeded"
    assert (
        state.steps_used == cut
        and state.tokens == started.state.tokens
        and state.cost == started.state.cost
    )
    with pytest.raises(OwnershipLost):
        await old.request(
            started.cursor,
            kind=kind,
            payload={},
            config=config,
            tool_name="fixture.info" if kind == "tool" else None,
        )
    async with sessions.begin() as session:
        assert await load_runtime_state(session, run_id) == state
        assert await session.scalar(
            select(func.count())
            .select_from(ModelInvocationRow)
            .where(ModelInvocationRow.run_id == run_id)
        ) == (1 if kind == "model" else 2)
        assert (
            await session.scalar(
                select(func.count()).select_from(ToolCallRow).where(ToolCallRow.run_id == run_id)
            )
            == 1
        )


async def test_last_failed_model_call_is_not_scheduled_again(
    database: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    sessions = async_sessionmaker(database)
    config = configuration(CALLS_PROFILE).model_copy(
        update={"model_retry": ModelRetryPolicy(max_retries=2)}
    )
    run_id = await seed(sessions, config)
    for attempt in (1, 2):
        claim = await claim_next(sessions, profile="calls-test", run_id=run_id)
        assert claim is not None
        state = await execute(
            run_id,
            claim.task,
            provider_name=config.provider,
            provider=TokenFixtureProvider(0),
            store=PostgresExecutionStore(sessions, claim=claim, expected_config=config),
            allow_model_retries=True,
        )
        assert state.tokens.attempts == attempt
        async with sessions.begin() as session:
            job = await session.get(JobRow, run_id)
            assert job is not None
            due = job.available_at

        async def now(session: AsyncSession, at: datetime = due) -> datetime:
            return at

        monkeypatch.setattr(jobs, "database_now", now)
        monkeypatch.setattr(execution, "database_now", now)
    assert state.error_code == "model_call_limit_exceeded" and state.retries_scheduled == 1
    async with sessions.begin() as session:
        models = list(
            await session.scalars(
                select(ModelInvocationRow).where(ModelInvocationRow.run_id == run_id)
            )
        )
        assert len(models) == 2 and all(row.error_code == "provider_rate_limited" for row in models)
        events = await HistoryRepository(session).events(run_id)
        assert sum(event.kind == "retry.scheduled" for event in events) == 1
        assert events[-2].payload == {"budget": "model_calls", "error_code": state.error_code}
        assert (await RunRepository(session).get(run_id)).status == RunStatus.FAILED


@pytest.mark.parametrize("kind", ["model", "tool"])
async def test_uncertain_last_intent_remains_interrupted(
    database: AsyncEngine, kind: Literal["model", "tool"]
) -> None:
    sessions = async_sessionmaker(database)
    config = configuration(CALLS_PROFILE).model_copy(update={"max_model_calls": 1})
    run_id = await seed(sessions, config)
    claim = await claim_next(sessions, profile="calls-test", run_id=run_id)
    assert claim is not None

    class Stop(PostgresExecutionStore):
        async def request(
            self,
            cursor: Cursor,
            *,
            kind: Literal["model", "tool"],
            payload: dict[str, JsonValue],
            config: RuntimeConfig,
            model_invocation_id: UUID | None = None,
            tool_name: str | None = None,
        ) -> Pending:
            pending = await super().request(
                cursor,
                kind=kind,
                payload=payload,
                config=config,
                model_invocation_id=model_invocation_id,
                tool_name=tool_name,
            )
            if kind == interrupted_kind:
                raise asyncio.CancelledError
            return pending

    interrupted_kind = kind
    with pytest.raises(asyncio.CancelledError):
        await execute(
            run_id,
            claim.task,
            provider_name=config.provider,
            provider=TokenFixtureProvider(2),
            store=Stop(sessions, claim=claim, expected_config=config),
            tools=fixture_registry(),
            tool_policy=POLICY,
        )
    await expire(sessions, run_id)
    replacement = await claim_next(sessions, profile="calls-test", run_id=run_id)
    assert replacement is not None
    state = await execute(
        run_id,
        replacement.task,
        provider_name=config.provider,
        provider=TokenFixtureProvider(2),
        store=PostgresExecutionStore(sessions, claim=replacement, expected_config=config),
        tools=fixture_registry(),
        tool_policy=POLICY,
    )
    assert state.error_code == "execution_interrupted" and state.tokens.attempts == 1
    assert state.steps_used == (1 if kind == "model" else 2)
    assert state.tokens.unknown_attempts == int(kind == "model")
    async with sessions.begin() as session:
        table = ModelInvocationRow if kind == "model" else ToolCallRow
        rows = list(await session.scalars(select(table).where(table.run_id == run_id)))
        assert len(rows) == 1 and isinstance(rows[0], (ModelInvocationRow, ToolCallRow))
        assert rows[0].error_code == "execution_interrupted"
