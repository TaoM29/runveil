"""Durable elapsed-time boundaries with a controlled database clock."""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID

import pytest
from runveil_core.agents import JsonValue
from runveil_core.models import (
    FinalResult,
    FinishAction,
    ModelRequest,
    ModelResponse,
    ProviderErrorCode,
)
from runveil_core.runs import RunStatus
from runveil_core.runtime import (
    Cursor,
    ElapsedBudgetExceeded,
    ModelRetryPolicy,
    Pending,
    RuntimeConfig,
    execute,
)
from runveil_core.scripted import ScriptedProvider
from runveil_core.tools import (
    FixtureInput,
    FixtureOutput,
    Permission,
    SideEffect,
    ToolRegistry,
    TypedTool,
)
from runveil_persistence import execution, jobs
from runveil_persistence.database import create_engine
from runveil_persistence.execution import PostgresExecutionStore, load_runtime_state
from runveil_persistence.history import HistoryRepository
from runveil_persistence.jobs import OwnershipLost, claim_next, enroll
from runveil_persistence.models import JobRow, ModelInvocationRow, ToolCallRow
from runveil_persistence.repositories import AgentRepository, RunRepository
from runveil_worker.worker import (
    BUDGET_PROFILE,
    POLICY,
    FixtureProvider,
    configuration,
    submit,
    work_once,
)
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@dataclass
class Clock:
    at: datetime | None = None


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    clock = Clock()
    real_now = jobs.database_now

    async def now(session: AsyncSession) -> datetime:
        return clock.at if clock.at is not None else await real_now(session)

    monkeypatch.setattr(jobs, "database_now", now)
    monkeypatch.setattr(execution, "database_now", now)
    return clock


async def deadline(sessions: async_sessionmaker[AsyncSession], run_id: UUID) -> datetime:
    async with sessions.begin() as session:
        job = await session.get(JobRow, run_id)
        assert job is not None and job.deadline_at is not None
        return job.deadline_at


async def test_deadline_survives_retries_and_restart(database: AsyncEngine, clock: Clock) -> None:
    sessions = async_sessionmaker(database)
    run_id = await submit(sessions, profile=BUDGET_PROFILE)
    async with sessions.begin() as session:
        job = await session.get(JobRow, run_id)
        assert job is not None and job.deadline_at is None
    for retries in (1, 2):
        restarted = create_engine(database.url)
        try:
            outcome = await work_once(
                async_sessionmaker(restarted), run_id=run_id, profile=BUDGET_PROFILE
            )
        finally:
            await restarted.dispose()
        assert outcome is not None and outcome[1].retries_scheduled == retries
        async with sessions.begin() as session:
            job = await session.get(JobRow, run_id)
            run = await RunRepository(session).get(run_id)
            assert job is not None and run.started_at is not None
            assert job.deadline_at == run.started_at + timedelta(seconds=30)
            clock.at = job.available_at
            with pytest.raises(IntegrityError):
                async with session.begin_nested():
                    await session.execute(
                        text("UPDATE worker_jobs SET deadline_at=NULL WHERE run_id=:id"),
                        {"id": run_id},
                    )
    original = await deadline(sessions, run_id)
    outcome = await work_once(sessions, run_id=run_id, profile=BUDGET_PROFILE)
    assert (
        outcome is not None and outcome[1].final_result is not None and outcome[1].steps_used == 5
    )
    assert await deadline(sessions, run_id) == original


@pytest.mark.parametrize("cancelled", [False, True])
async def test_expired_backoff_is_claimable_before_retry_due(
    database: AsyncEngine, clock: Clock, cancelled: bool
) -> None:
    sessions = async_sessionmaker(database)
    config = configuration(BUDGET_PROFILE).model_copy(
        update={
            "max_elapsed_seconds": 1,
            "model_retry": ModelRetryPolicy(max_retries=2, base_delay_seconds=60),
        }
    )
    async with sessions.begin() as session:
        agents = AgentRepository(session)
        agent = await agents.create("Elapsed budget fixture")
        version = await agents.create_version(agent.id, config.model_dump(mode="json"))
        run_id = (await RunRepository(session).create(version.id)).id
        await enroll(session, run_id, task="Public fixture", profile="budget-test-v1")
    claim = await claim_next(sessions, profile="budget-test-v1", run_id=run_id)
    assert claim is not None
    state = await execute(
        run_id,
        claim.task,
        provider_name=config.provider,
        provider=ScriptedProvider([ProviderErrorCode.RATE_LIMITED]),
        store=PostgresExecutionStore(sessions, claim=claim, expected_config=config),
        allow_model_retries=True,
    )
    assert state.retries_scheduled == 1 and state.error_code is None
    clock.at = await deadline(sessions, run_id)
    async with sessions.begin() as session:
        job = await session.get(JobRow, run_id)
        assert job is not None and job.available_at > clock.at
        if cancelled:
            run = await RunRepository(session).get(run_id)
            await RunRepository(session).transition(
                run_id, RunStatus.CANCELLED, expected_revision=run.revision
            )
    replacement = await claim_next(sessions, profile="budget-test-v1", run_id=run_id)
    if cancelled:
        assert replacement is None
        return
    assert replacement is not None
    provider = ScriptedProvider([])
    state = await execute(
        run_id,
        replacement.task,
        provider_name=config.provider,
        provider=provider,
        store=PostgresExecutionStore(sessions, claim=replacement, expected_config=config),
        allow_model_retries=True,
    )
    assert state.error_code == "elapsed_time_exceeded" and state.steps_used == 1
    assert not provider.requests and state.retries_scheduled == 1
    assert await claim_next(sessions, profile="budget-test-v1", run_id=run_id) is None


@pytest.mark.parametrize(
    "point,steps,calls",
    [
        ("before_request", 0, []),
        ("model_intent", 1, []),
        ("tool_intent", 2, ["model"]),
        ("late_model", 1, ["model"]),
        ("late_tool", 2, ["model", "tool"]),
        ("timeout_model", 1, ["model"]),
        ("timeout_tool", 2, ["model", "tool"]),
    ],
)
async def test_expiry_at_dispatch_and_result_boundaries(
    database: AsyncEngine, clock: Clock, point: str, steps: int, calls: list[str]
) -> None:
    sessions = async_sessionmaker(database)
    run_id = await submit(sessions, profile=BUDGET_PROFILE)
    claim = await claim_next(sessions, profile=BUDGET_PROFILE, run_id=run_id)
    assert claim is not None
    dispatched: list[str] = []

    class Store(PostgresExecutionStore):
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
            if point == "before_request":
                clock.at = await deadline(sessions, run_id)
            pending = await super().request(
                cursor,
                kind=kind,
                payload=payload,
                config=config,
                model_invocation_id=model_invocation_id,
                tool_name=tool_name,
            )
            if point == f"{kind}_intent":
                clock.at = await deadline(sessions, run_id)
            if point == f"timeout_{kind}":
                clock.at = await deadline(sessions, run_id) - timedelta(milliseconds=5)
            return pending

    async def effect(kind: str) -> None:
        dispatched.append(kind)
        if point == f"late_{kind}":
            clock.at = await deadline(sessions, run_id)
        if point == f"timeout_{kind}":
            try:
                await asyncio.Event().wait()
            finally:
                clock.at = await deadline(sessions, run_id)

    class Provider(FixtureProvider):
        async def generate(self, request: ModelRequest) -> ModelResponse:
            await effect("model")
            if point == "late_model":
                return ModelResponse(
                    model="fixture-v1",
                    content=FinishAction(
                        action="finish",
                        result=FinalResult(summary="late-result-sentinel", artifacts=()),
                    ).model_dump_json(),
                    finish_reason="stop",
                    latency_ms=0.0,
                )
            return await super().generate(request)

    async def handler(arguments: FixtureInput) -> FixtureOutput:
        await effect("tool")
        return FixtureOutput(project="Runveil", fixture_version=1)

    tools = ToolRegistry(
        (
            TypedTool(
                name="fixture.info",
                description="Public fixture",
                input_type=FixtureInput,
                output_type=FixtureOutput,
                handler=handler,
                permission=Permission.READ,
                side_effect=SideEffect.READ_ONLY,
                timeout_seconds=60.0,
            ),
        )
    )
    state = await execute(
        run_id,
        claim.task,
        provider_name=configuration(BUDGET_PROFILE).provider,
        provider=Provider(),
        store=Store(sessions, claim=claim, expected_config=configuration(BUDGET_PROFILE)),
        tools=tools,
        tool_policy=POLICY,
        allow_model_retries=True,
    )
    assert state.error_code == "elapsed_time_exceeded" and state.final_result is None
    assert state.steps_used == steps and dispatched == calls
    assert "late-result-sentinel" not in state.model_dump_json()
    async with sessions.begin() as session:
        assert await load_runtime_state(session, run_id) == state
        assert (await RunRepository(session).get(run_id)).status == RunStatus.FAILED
        models = list(
            await session.scalars(
                select(ModelInvocationRow).where(ModelInvocationRow.run_id == run_id)
            )
        )
        tools_rows = list(
            await session.scalars(select(ToolCallRow).where(ToolCallRow.run_id == run_id))
        )
        assert len(models) + len(tools_rows) == steps
        if tools_rows:
            assert (
                tools_rows[-1].result is None
                and tools_rows[-1].error_code == "elapsed_time_exceeded"
            )
        elif models:
            assert models[-1].result is None and models[-1].error_code == "elapsed_time_exceeded"
        assert all(record.status != "REQUESTED" for record in models)
        assert all(record.status != "REQUESTED" for record in tools_rows)
        events = await HistoryRepository(session).events(run_id)
        assert [event.kind for event in events[-2:]] == ["budget.exceeded", "run.transitioned"]
        assert sum(event.kind == "budget.exceeded" for event in events) == 1
        assert [event.sequence for event in events] == list(range(1, len(events) + 1))


async def test_expiry_rollback_and_stale_owner_fence(
    database: AsyncEngine, clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    sessions = async_sessionmaker(database)
    run_id = await submit(sessions, profile=BUDGET_PROFILE)
    claim = await claim_next(sessions, profile=BUDGET_PROFILE, run_id=run_id)
    assert claim is not None
    config = configuration(BUDGET_PROFILE)
    store = PostgresExecutionStore(sessions, claim=claim, expected_config=config)
    started = await store.start(run_id, claim.task, config.provider)
    pending = await store.request(started.cursor, kind="model", payload={}, config=config)
    clock.at = await deadline(sessions, run_id)
    assert await claim_next(sessions, profile=BUDGET_PROFILE, run_id=run_id) is None

    async def interrupt(
        self: RunRepository,
        run_id: UUID,
        target: RunStatus,
        *,
        expected_revision: int,
        expected_sequence: int | None = None,
    ) -> object:
        raise asyncio.CancelledError

    with monkeypatch.context() as patch:
        patch.setattr(RunRepository, "transition", interrupt)
        with pytest.raises(asyncio.CancelledError):
            await store.complete(pending, started.state, result={"late": "discard"})
    async with sessions.begin() as session:
        record = await session.get(ModelInvocationRow, pending.id)
        assert record is not None and record.status == "REQUESTED"
        assert await load_runtime_state(session, run_id) == started.state
    clock.at += timedelta(seconds=jobs.LEASE_SECONDS)
    replacement = await claim_next(sessions, profile=BUDGET_PROFILE, run_id=run_id)
    assert replacement is not None
    with pytest.raises(OwnershipLost):
        await store.complete(pending, started.state, result={"late": "discard"})
    fresh = PostgresExecutionStore(sessions, claim=replacement, expected_config=config)
    with pytest.raises(ElapsedBudgetExceeded) as caught:
        await fresh.complete(pending, started.state, result={"late": "discard"})
    assert caught.value.state.steps_used == 1
    async with sessions.begin() as session:
        assert await load_runtime_state(session, run_id) == caught.value.state
        assert (await RunRepository(session).get(run_id)).status == RunStatus.FAILED
