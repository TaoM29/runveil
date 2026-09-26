import asyncio
from uuid import UUID, uuid4

import pytest
from alembic import command
from conftest import migration_config
from runveil_core.errors import InvalidTransition, NotFound, RevisionConflict
from runveil_core.invocations import InvocationStatus, ModelInvocation
from runveil_core.runs import Run, RunStatus
from runveil_persistence.database import create_engine
from runveil_persistence.history import HistoryRepository
from runveil_persistence.invocations import InvocationRepository
from runveil_persistence.repositories import RunRepository
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from test_persistence import seed

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def start(database: AsyncEngine) -> Run:
    _, run = await seed(database)
    async with async_sessionmaker(database).begin() as session:
        return await RunRepository(session).transition(
            run.id, RunStatus.RUNNING, expected_revision=0
        )


async def request_model(database: AsyncEngine, run_id: UUID) -> ModelInvocation:
    async with async_sessionmaker(database).begin() as session:
        return await InvocationRepository(session).request_model(
            run_id,
            invocation_id=uuid4(),
            provider="fixture",
            model="scripted",
            request={"messages": [{"content": "Fixture"}]},
            expected_revision=1,
            expected_sequence=2,
        )


async def test_model_tool_outcomes_restore_with_history(database: AsyncEngine) -> None:
    run = await start(database)
    requested = await request_model(database, run.id)
    async with async_sessionmaker(database).begin() as session:
        repo = InvocationRepository(session)
        model = await repo.complete_model(
            run.id,
            requested.id,
            result={"tool_calls": [{"name": "fixture.read"}]},
            state={"next": "tool"},
            expected_revision=1,
            expected_sequence=3,
        )
        assert requested.status == InvocationStatus.REQUESTED  # Detached snapshot stays unchanged.
        assert model.status == InvocationStatus.SUCCEEDED and model.step_number == 1
        tool = await repo.request_tool(
            run.id,
            tool_call_id=uuid4(),
            tool_name="fixture.read",
            arguments={"path": "fixture"},
            model_invocation_id=model.id,
            expected_revision=1,
            expected_sequence=6,
        )
    second = create_engine(database.url)
    try:
        async with async_sessionmaker(second).begin() as session:
            repo = InvocationRepository(session)
            assert await repo.get_model(run.id, model.id) == model
            assert await repo.get_tool(run.id, tool.id) == tool
            failed = await repo.complete_tool(
                run.id,
                tool.id,
                error_code="fixture_failure",
                state={"handled": True},
                expected_revision=1,
                expected_sequence=7,
            )
            assert failed.result is None and failed.status == InvocationStatus.FAILED
            assert failed.error_code == "fixture_failure" and failed.step_number == 2
            assert failed.completed_at is not None and failed.completed_at >= failed.requested_at
            history = HistoryRepository(session)
            checkpoint = await history.latest_checkpoint(run.id)
            assert checkpoint is not None and checkpoint.event_sequence == 10
            assert checkpoint.state == {"handled": True}
            events = await history.events(run.id)
            assert [e.kind for e in events] == [
                "run.created",
                "run.transitioned",
                "model.requested",
                "model.completed",
                "step.recorded",
                "checkpoint.created",
                "tool.requested",
                "tool.failed",
                "step.recorded",
                "checkpoint.created",
            ]
            assert events[3].payload == {"record_id": str(model.id)}
            assert events[7].payload == {"record_id": str(tool.id)}
            assert [step.details for step in await history.steps(run.id)] == [
                {"record_id": str(model.id)},
                {"record_id": str(tool.id)},
            ]
            await RunRepository(session).transition(
                run.id,
                RunStatus.FAILED,
                expected_revision=1,
                expected_sequence=10,
            )
        async with async_sessionmaker(second).begin() as session:
            assert await InvocationRepository(session).get_tool(run.id, tool.id) == failed
    finally:
        await second.dispose()


async def test_rollback_validation_and_unresolved_intent(database: AsyncEngine) -> None:
    run = await start(database)
    factory = async_sessionmaker(database)
    async with factory() as session:
        transient = await InvocationRepository(session).request_tool(
            run.id,
            tool_call_id=uuid4(),
            tool_name="fixture",
            arguments={},
            expected_revision=1,
            expected_sequence=2,
        )
        await session.rollback()
    async with factory.begin() as session:
        with pytest.raises(NotFound):
            await InvocationRepository(session).get_tool(run.id, transient.id)
        assert len(await HistoryRepository(session).events(run.id)) == 2
    requested = await request_model(database, run.id)
    async with factory() as session:
        repo = InvocationRepository(session)
        with pytest.raises(ValueError):
            await repo.complete_model(
                run.id,
                requested.id,
                result={},
                state={"invalid": float("nan")},
                expected_revision=1,
                expected_sequence=3,
            )
        assert len(await HistoryRepository(session).events(run.id)) == 3
        await repo.complete_model(
            run.id,
            requested.id,
            result={},
            state={},
            expected_revision=1,
            expected_sequence=3,
        )
        async with factory.begin() as observer:
            assert await InvocationRepository(observer).get_model(run.id, requested.id) == requested
            assert await HistoryRepository(observer).latest_checkpoint(run.id) is None
        await session.rollback()
    async with factory.begin() as session:
        repo = InvocationRepository(session)
        assert await repo.get_model(run.id, requested.id) == requested
        assert await HistoryRepository(session).steps(run.id) == []
        with pytest.raises(RevisionConflict):
            await repo.complete_model(
                run.id, requested.id, result={}, state={}, expected_revision=1, expected_sequence=2
            )
        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                await repo.request_model(
                    run.id,
                    invocation_id=requested.id,
                    provider="fixture",
                    model="different",
                    request={},
                    expected_revision=1,
                    expected_sequence=3,
                )
        assert len(await HistoryRepository(session).events(run.id)) == 3
        await RunRepository(session).transition(run.id, RunStatus.CANCELLED, expected_revision=1)
        with pytest.raises(InvalidTransition):
            await repo.complete_model(
                run.id, requested.id, result={}, state={}, expected_revision=2, expected_sequence=4
            )
        assert await repo.get_model(run.id, requested.id) == requested


async def test_competing_completions_have_one_immutable_outcome(database: AsyncEngine) -> None:
    run = await start(database)
    requested = await request_model(database, run.id)

    async def complete() -> ModelInvocation | RevisionConflict:
        try:
            async with async_sessionmaker(database).begin() as session:
                return await InvocationRepository(session).complete_model(
                    run.id,
                    requested.id,
                    error_code="fixture_failure",
                    state={},
                    expected_revision=1,
                    expected_sequence=3,
                )
        except RevisionConflict as error:
            return error

    results = await asyncio.wait_for(asyncio.gather(complete(), complete()), timeout=10)
    assert sum(isinstance(r, ModelInvocation) for r in results) == 1
    assert sum(isinstance(r, RevisionConflict) for r in results) == 1
    async with async_sessionmaker(database).begin() as session:
        repo = InvocationRepository(session)
        with pytest.raises(InvalidTransition):
            await repo.complete_model(
                run.id, requested.id, result={}, state={}, expected_revision=1, expected_sequence=6
            )
        assert len(await HistoryRepository(session).steps(run.id)) == 1
        assert len(await HistoryRepository(session).events(run.id)) == 6


async def test_source_and_sql_integrity_guards(database: AsyncEngine) -> None:
    run, other = await start(database), await start(database)
    requested = await request_model(database, run.id)
    async with async_sessionmaker(database).begin() as session:
        repo = InvocationRepository(session)
        with pytest.raises(NotFound):
            await repo.get_model(other.id, requested.id)
        for target, error, cursor in [(other.id, NotFound, 2), (run.id, InvalidTransition, 3)]:
            with pytest.raises(error):
                await repo.request_tool(
                    target,
                    tool_call_id=uuid4(),
                    tool_name="fixture",
                    arguments={},
                    model_invocation_id=requested.id,
                    expected_revision=1,
                    expected_sequence=cursor,
                )
        model = await repo.complete_model(
            run.id, requested.id, result={}, state={}, expected_revision=1, expected_sequence=3
        )
        tool = await repo.request_tool(
            run.id,
            tool_call_id=uuid4(),
            tool_name="fixture",
            arguments={},
            model_invocation_id=model.id,
            expected_revision=1,
            expected_sequence=6,
        )
        # A real successful tool boundary exercises the other outcome shape/table.
        tool = await repo.complete_tool(
            run.id,
            tool.id,
            result={"content": "fixture"},
            state={},
            expected_revision=1,
            expected_sequence=7,
        )
        for table, record_id in [("model_invocations", model.id), ("tool_calls", tool.id)]:
            for sql in [
                f"DELETE FROM {table} WHERE id=:id",
                f"UPDATE {table} SET result='{{}}'::jsonb WHERE id=:id",
            ]:
                with pytest.raises(IntegrityError):
                    async with session.begin_nested():
                        await session.execute(text(sql), {"id": record_id})
        pending = await repo.request_tool(
            run.id,
            tool_call_id=uuid4(),
            tool_name="fixture",
            arguments={},
            expected_revision=1,
            expected_sequence=10,
        )
        for assignment in [
            "status='SUCCEEDED', result='{}'::jsonb",  # Missing event and checkpoint.
            "status='SUCCEEDED', result='{}'::jsonb, completed_event_sequence=8, step_number=2",
            "status='SUCCEEDED', result='{}'::jsonb, tool_name='changed'",
            "status='FAILED', result='{}'::jsonb, error_code='fixture_failure'",
        ]:
            with pytest.raises(IntegrityError):
                async with session.begin_nested():
                    await session.execute(
                        text(f"UPDATE tool_calls SET {assignment} WHERE id=:id"), {"id": pending.id}
                    )
        # Direct SQL source links cannot reach another run, even with a matching request event.
        other_tool_id = uuid4()
        with pytest.raises(IntegrityError, match="source model"):
            async with session.begin_nested():
                event_sequence = await session.scalar(
                    text(
                        "INSERT INTO execution_events (run_id, kind, run_revision, payload) "
                        "VALUES (:run, 'tool.requested', 1, jsonb_build_object('record_id', "
                        "CAST(:id AS text))) RETURNING sequence"
                    ),
                    {"run": other.id, "id": other_tool_id},
                )
                await session.execute(
                    text(
                        "INSERT INTO tool_calls (id, run_id, requested_event_sequence, request, "
                        "tool_name, model_invocation_id, requested_at) "
                        "VALUES (:id, :run, :seq, '{}', 'fixture', :source, clock_timestamp())"
                    ),
                    {
                        "id": other_tool_id,
                        "run": other.id,
                        "seq": event_sequence,
                        "source": model.id,
                    },
                )
        assert await repo.get_tool(run.id, pending.id) == pending


async def test_populated_1b_upgrade_and_downgrade(empty_database: AsyncEngine) -> None:
    async with empty_database.begin() as connection:
        await connection.run_sync(lambda conn: command.upgrade(migration_config(conn), "0002"))
    run = await start(empty_database)
    async with async_sessionmaker(empty_database).begin() as session:
        checkpoint = await HistoryRepository(session).record_step(
            run.id,
            kind="fixture",
            details={},
            state={"fixture": True},
            expected_revision=1,
            expected_sequence=2,
        )
    async with empty_database.begin() as connection:
        await connection.run_sync(lambda conn: command.upgrade(migration_config(conn), "head"))
        await connection.run_sync(lambda conn: command.check(migration_config(conn)))
    async with async_sessionmaker(empty_database).begin() as session:
        assert await HistoryRepository(session).latest_checkpoint(run.id) == checkpoint
        record = await InvocationRepository(session).request_model(
            run.id,
            invocation_id=uuid4(),
            provider="fixture",
            model="scripted",
            request={},
            expected_revision=1,
            expected_sequence=4,
        )
        await InvocationRepository(session).complete_model(
            run.id,
            record.id,
            result={},
            state={},
            expected_revision=1,
            expected_sequence=5,
        )
        events = await HistoryRepository(session).events(run.id)
    async with empty_database.begin() as connection:
        await connection.run_sync(lambda conn: command.downgrade(migration_config(conn), "0002"))
        await connection.run_sync(lambda conn: command.upgrade(migration_config(conn), "head"))
        await connection.run_sync(lambda conn: command.check(migration_config(conn)))
    async with async_sessionmaker(empty_database).begin() as session:
        assert await HistoryRepository(session).events(run.id) == events
        with pytest.raises(NotFound):
            await InvocationRepository(session).get_model(run.id, record.id)
