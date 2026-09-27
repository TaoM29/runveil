"""Real database crash-boundary, duplicate delivery and ownership evidence."""

import asyncio
from typing import Literal
from uuid import UUID

import pytest
from runveil_core.agents import JsonValue
from runveil_core.errors import RevisionConflict
from runveil_core.models import ToolAction
from runveil_core.runs import RunStatus
from runveil_core.runtime import Cursor, Pending, RuntimeConfig, RuntimeState, Started, execute
from runveil_core.tools import fixture_registry
from runveil_persistence.database import create_engine
from runveil_persistence.execution import PostgresExecutionStore, load_runtime_state
from runveil_persistence.history import HistoryRepository
from runveil_persistence.jobs import OwnershipLost, claim_next, enroll
from runveil_persistence.models import EventRow, JobRow, ModelInvocationRow, ToolCallRow
from runveil_persistence.repositories import RunRepository
from runveil_worker.worker import POLICY, PROFILE, FixtureProvider, configuration, submit, work_once
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def expire(sessions: async_sessionmaker[AsyncSession], run_id: UUID) -> None:
    # Advance the lease boundary deterministically, without wall-clock sleeps.
    async with sessions.begin() as session:
        await session.execute(
            text("UPDATE worker_jobs SET expires_at=clock_timestamp() WHERE run_id=:id"),
            {"id": run_id},
        )


@pytest.mark.parametrize(
    "boundary,steps,error",
    [
        ("started", 3, None),
        ("model.requested", 1, "execution_interrupted"),
        ("model.completed", 3, None),
        ("tool.requested", 2, "execution_interrupted"),
        ("tool.completed", 3, None),
        ("finished", 3, None),
    ],
)
async def test_restart_at_committed_boundaries(
    database: AsyncEngine, boundary: str, steps: int, error: str | None
) -> None:
    sessions = async_sessionmaker(database)
    run_id = await submit(sessions)
    claim = await claim_next(sessions, profile=PROFILE, run_id=run_id)
    assert claim is not None

    class CrashStore(PostgresExecutionStore):
        async def start(self, run_id: UUID, task: str, provider: str) -> Started:
            started = await super().start(run_id, task, provider)
            if boundary == "started":
                raise asyncio.CancelledError
            return started

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
            if boundary == f"{kind}.requested":
                raise asyncio.CancelledError
            return pending

        async def complete(
            self,
            pending: Pending,
            state: RuntimeState,
            *,
            result: dict[str, JsonValue] | None = None,
            error_code: str | None = None,
        ) -> Cursor:
            cursor = await super().complete(pending, state, result=result, error_code=error_code)
            point = "finished" if state.final_result else f"{pending.kind}.completed"
            if boundary == point:
                raise asyncio.CancelledError
            return cursor

    with pytest.raises(asyncio.CancelledError):
        await execute(
            run_id,
            claim.task,
            provider_name=configuration().provider,
            provider=FixtureProvider(),
            tools=fixture_registry(),
            tool_policy=POLICY,
            store=CrashStore(sessions, claim=claim, expected_config=configuration()),
        )
    assert await work_once(sessions, run_id=run_id) is None
    await expire(sessions, run_id)
    # Recreate the engine and all execution objects, as a new worker process would.
    restarted = create_engine(database.url)
    try:
        outcome = await work_once(async_sessionmaker(restarted), run_id=run_id)
        assert (outcome is None) == (boundary == "finished")
    finally:
        await restarted.dispose()
    assert await work_once(sessions, run_id=run_id) is None
    async with sessions.begin() as session:
        state = await load_runtime_state(session, run_id)
        assert state is not None and state.steps_used == steps and state.error_code == error
        run = await RunRepository(session).get(run_id)
        assert run.status == (RunStatus.FAILED if error else RunStatus.SUCCEEDED)
        models = list(
            await session.scalars(
                select(ModelInvocationRow)
                .where(ModelInvocationRow.run_id == run_id)
                .order_by(ModelInvocationRow.requested_event_sequence)
            )
        )
        tools = list(await session.scalars(select(ToolCallRow).where(ToolCallRow.run_id == run_id)))
        assert len(models) + len(tools) == steps
        assert all(record.status != "REQUESTED" for record in models)
        assert all(record.status != "REQUESTED" for record in tools)
        if tools:
            assert tools[0].model_invocation_id == models[0].id
        if not error:
            assert [message.role for message in state.messages] == [
                "system",
                "user",
                "assistant",
                "tool",
                "assistant",
            ]
        events = await HistoryRepository(session).events(run_id)
        assert [event.sequence for event in events] == list(range(1, len(events) + 1))
        assert events[-1].kind == "run.transitioned"


async def test_claim_competition_expiry_and_all_write_fences(database: AsyncEngine) -> None:
    sessions = async_sessionmaker(database)
    run_id = await submit(sessions)
    claims = await asyncio.gather(
        *(claim_next(sessions, profile=PROFILE, run_id=run_id) for _ in range(2))
    )
    owners = [claim for claim in claims if claim is not None]
    assert len(owners) == 1
    claim = owners[0]
    store = PostgresExecutionStore(sessions, claim=claim, expected_config=configuration())
    with pytest.raises(OwnershipLost):
        await PostgresExecutionStore(sessions).start(run_id, claim.task, configuration().provider)
    started = await store.start(run_id, claim.task, configuration().provider)
    pending = await store.request(started.cursor, kind="model", payload={}, config=started.config)
    await expire(sessions, run_id)
    failed = started.state.model_copy(
        update={"steps_used": 1, "error_code": "execution_interrupted"}
    )
    with pytest.raises(OwnershipLost):
        await store.complete(pending, failed, error_code="execution_interrupted")
    replacement = await claim_next(sessions, profile=PROFILE, run_id=run_id)
    assert replacement is not None and replacement.token != claim.token
    for operation in (
        store.start(run_id, claim.task, configuration().provider),
        store.request(pending.cursor, kind="model", payload={}, config=started.config),
        store.complete(pending, failed, error_code="execution_interrupted"),
        store.exhaust(pending.cursor, failed),
    ):
        with pytest.raises(OwnershipLost):
            await operation
    # Fresh ownership still cannot override lifecycle cancellation.
    fresh = PostgresExecutionStore(sessions, claim=replacement, expected_config=configuration())
    async with sessions.begin() as session:
        await RunRepository(session).transition(
            run_id,
            RunStatus.CANCELLED,
            expected_revision=started.cursor.revision,
            expected_sequence=pending.cursor.sequence,
        )
    with pytest.raises(RevisionConflict):
        await fresh.complete(pending, failed, error_code="execution_interrupted")
    assert await work_once(sessions, run_id=run_id) is None


async def test_enrollment_atomicity_identity_and_profile_refusal(database: AsyncEngine) -> None:
    sessions = async_sessionmaker(database)
    run_id = await submit(sessions)
    async with sessions.begin() as session:
        job = await session.get(JobRow, run_id)
        assert job is not None
        await enroll(session, run_id, task=job.task, profile=PROFILE)
        with pytest.raises(ValueError):
            await enroll(session, run_id, task="Changed task", profile=PROFILE)
        assert await session.scalar(select(func.count()).select_from(JobRow)) == 1
        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                await session.execute(
                    text("UPDATE worker_jobs SET profile='changed' WHERE run_id=:id"),
                    {"id": run_id},
                )
    assert await claim_next(sessions, profile="unknown") is None
    claim = await claim_next(sessions, profile=PROFILE)
    assert claim is not None
    store = PostgresExecutionStore(
        sessions, claim=claim, expected_config=configuration().model_copy(update={"model": "wrong"})
    )
    with pytest.raises(ValueError, match="profile"):
        await store.start(run_id, claim.task, configuration().provider)
    async with sessions.begin() as session:
        assert (await RunRepository(session).get(run_id)).status == RunStatus.QUEUED
        assert await load_runtime_state(session, run_id) is None


@pytest.mark.parametrize("corruption", ["legacy", "tail", "provenance"])
async def test_recovery_refuses_unsupported_or_inconsistent_history(
    database: AsyncEngine, corruption: str
) -> None:
    sessions = async_sessionmaker(database)
    run_id = await submit(sessions)
    claim = await claim_next(sessions, profile=PROFILE, run_id=run_id)
    assert claim is not None
    store = PostgresExecutionStore(sessions, claim=claim, expected_config=configuration())
    started = await store.start(run_id, claim.task, configuration().provider)
    async with sessions.begin() as session:
        state = started.state.model_dump(mode="json")
        if corruption == "legacy":
            state["schema_version"] = 1
        elif corruption == "provenance":
            state["next_tool"] = ToolAction(
                action="tool_call", tool_name="fixture.info", arguments={}, decision_summary="Read"
            ).model_dump(mode="json")
        if corruption == "tail":
            session.add(
                EventRow(
                    run_id=run_id,
                    kind="unexpected.event",
                    run_revision=started.cursor.revision,
                    payload={},
                )
            )
        else:
            await HistoryRepository(session).record_step(
                run_id,
                kind="test.unsupported_state",
                details={},
                state=state,
                expected_revision=started.cursor.revision,
                expected_sequence=started.cursor.sequence,
            )
    await expire(sessions, run_id)
    with pytest.raises(ValueError):
        await work_once(sessions, run_id=run_id)
    async with sessions.begin() as session:
        assert (await RunRepository(session).get(run_id)).status == RunStatus.RUNNING
        assert await session.scalar(select(func.count()).select_from(ModelInvocationRow)) == 0
