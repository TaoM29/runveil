import asyncio
from uuid import uuid4

import pytest
from alembic import command
from conftest import migration_config
from runveil_core.errors import InvalidTransition, NotFound, RevisionConflict
from runveil_core.history import Checkpoint
from runveil_core.runs import RunStatus
from runveil_persistence.database import create_engine
from runveil_persistence.history import HistoryRepository
from runveil_persistence.repositories import RunRepository
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from test_persistence import seed

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_history_and_checkpoint_restore_across_connections(database: AsyncEngine) -> None:
    version, run = await seed(database)
    factory = async_sessionmaker(database)
    async with factory.begin() as session:
        history = HistoryRepository(session)
        assert await history.latest_checkpoint(run.id) is None
        await RunRepository(session).transition(run.id, RunStatus.RUNNING, expected_revision=0)
        checkpoint = await history.record_step(
            run.id,
            kind="fixture.response",
            details={"summary": "Fixture only"},
            state={"messages": [{"role": "assistant", "content": "done"}], "iteration": 1},
            expected_revision=1,
            expected_sequence=2,
        )
        await RunRepository(session).transition(
            run.id,
            RunStatus.WAITING_FOR_APPROVAL,
            expected_revision=1,
            expected_sequence=checkpoint.event_sequence,
        )
    second_engine = create_engine(database.url)
    try:
        async with async_sessionmaker(second_engine).begin() as session:
            history = HistoryRepository(session)
            restored = await history.latest_checkpoint(run.id)
            assert restored == checkpoint
            assert restored is not None
            assert restored.schema_version == 1 and restored.run_revision == 1
            assert restored.run_status == RunStatus.RUNNING
            current = await RunRepository(session).get(run.id)
            assert current.agent_version_id == version.id
            assert current.status == RunStatus.WAITING_FOR_APPROVAL and current.revision == 2
            events = await history.events(run.id, limit=3)
            events += await history.events(run.id, after_sequence=events[-1].sequence)
            assert [e.sequence for e in events] == [1, 2, 3, 4, 5]
            assert [e.kind for e in events] == [
                "run.created",
                "run.transitioned",
                "step.recorded",
                "checkpoint.created",
                "run.transitioned",
            ]
            assert [e.run_revision for e in events] == [0, 1, 1, 1, 2]
            assert events[-1].payload["from_status"] == "RUNNING"
            assert events[-1].payload["status"] == "WAITING_FOR_APPROVAL"
            assert [
                e.sequence
                for e in await history.events(run.id, after_sequence=restored.event_sequence)
            ] == [5]
            steps = await history.steps(run.id)
            assert [(s.number, s.kind) for s in steps] == [(1, "fixture.response")]
            assert steps[0].details == {"summary": "Fixture only"}
            assert restored.state["iteration"] == 1
            state_copy = restored.state
            state_copy["messages"] = []
            assert restored.state == checkpoint.state
    finally:
        await second_engine.dispose()


async def test_atomic_rollback_and_stale_decisions(database: AsyncEngine) -> None:
    _, run = await seed(database)
    factory = async_sessionmaker(database)
    async with factory.begin() as session:
        await RunRepository(session).transition(run.id, RunStatus.RUNNING, expected_revision=0)
    async with factory() as session:
        checkpoint = await HistoryRepository(session).record_step(
            run.id,
            kind="fixture",
            details={},
            state={"iteration": 1},
            expected_revision=1,
            expected_sequence=2,
        )
        await RunRepository(session).transition(
            run.id,
            RunStatus.SUCCEEDED,
            expected_revision=1,
            expected_sequence=checkpoint.event_sequence,
        )
        # Uncommitted boundary and lifecycle changes are invisible to another reader.
        async with factory.begin() as observer:
            assert await HistoryRepository(observer).latest_checkpoint(run.id) is None
            assert len(await HistoryRepository(observer).events(run.id)) == 2
            assert (await RunRepository(observer).get(run.id)).status == RunStatus.RUNNING
        await session.rollback()
    async with factory.begin() as session:
        history = HistoryRepository(session)
        assert await history.latest_checkpoint(run.id) is None
        assert await history.steps(run.id) == []
        assert len(await history.events(run.id)) == 2
        assert (await RunRepository(session).get(run.id)).status == RunStatus.RUNNING
        checkpoint = await history.record_step(
            run.id,
            kind="fixture",
            details={},
            state={},
            expected_revision=1,
            expected_sequence=2,
        )
        assert checkpoint.event_sequence == 4 and checkpoint.step_number == 1
        with pytest.raises(RevisionConflict):
            await history.record_step(
                run.id,
                kind="fixture",
                details={},
                state={},
                expected_revision=1,
                expected_sequence=2,
            )
        with pytest.raises(RevisionConflict):
            await RunRepository(session).transition(
                run.id,
                RunStatus.SUCCEEDED,
                expected_revision=1,
                expected_sequence=2,
            )
        second = await history.record_step(
            run.id,
            kind="fixture",
            details={},
            state={"iteration": 2},
            expected_revision=1,
            expected_sequence=4,
        )
        assert second.step_number == 2 and second.event_sequence == 6
        assert await history.latest_checkpoint(run.id) == second


async def test_competing_boundaries_have_one_winner(database: AsyncEngine) -> None:
    _, run = await seed(database)
    factory = async_sessionmaker(database)
    async with factory.begin() as session:
        await RunRepository(session).transition(run.id, RunStatus.RUNNING, expected_revision=0)

    async def append() -> Checkpoint | RevisionConflict:
        try:
            async with factory.begin() as session:
                return await HistoryRepository(session).record_step(
                    run.id,
                    kind="fixture",
                    details={},
                    state={},
                    expected_revision=1,
                    expected_sequence=2,
                )
        except RevisionConflict as error:
            return error

    results = await asyncio.wait_for(asyncio.gather(append(), append()), timeout=10)
    assert sum(isinstance(result, Checkpoint) for result in results) == 1
    assert sum(isinstance(result, RevisionConflict) for result in results) == 1
    async with factory.begin() as session:
        assert [e.sequence for e in await HistoryRepository(session).events(run.id)] == [1, 2, 3, 4]


async def test_boundary_guards_and_untrusted_inputs(database: AsyncEngine) -> None:
    _, run = await seed(database)
    _, other = await seed(database)
    async with async_sessionmaker(database).begin() as session:
        history = HistoryRepository(session)
        with pytest.raises(NotFound):
            await history.latest_checkpoint(uuid4())
        with pytest.raises(InvalidTransition):
            await history.record_step(
                run.id,
                kind="fixture",
                details={},
                state={},
                expected_revision=0,
                expected_sequence=1,
            )
        await RunRepository(session).transition(run.id, RunStatus.RUNNING, expected_revision=0)
        with pytest.raises(ValueError):
            await history.record_step(
                run.id,
                kind="fixture",
                details={},
                state={"invalid": float("nan")},
                expected_revision=1,
                expected_sequence=2,
            )
        checkpoint = await history.record_step(
            run.id,
            kind="fixture",
            details={},
            state={},
            expected_revision=1,
            expected_sequence=2,
        )
        for table in ("execution_events", "run_steps", "checkpoints"):
            for sql in (
                f"DELETE FROM {table} WHERE run_id=:id",
                f"UPDATE {table} SET created_at=clock_timestamp() WHERE run_id=:id",
            ):
                with pytest.raises(IntegrityError, match="immutable"):
                    async with session.begin_nested():
                        await session.execute(text(sql), {"id": run.id})
        # A matching event in a different run cannot satisfy a checkpoint's reference.
        await RunRepository(session).transition(other.id, RunStatus.RUNNING, expected_revision=0)
        bad_statements = [
            "INSERT INTO execution_events (run_id, sequence, kind, run_revision, payload) "
            "VALUES (:id, 99, 'fixture', 1, '{}')",
            "INSERT INTO run_steps (run_id, number, kind, details) "
            "VALUES (:id, 9, 'fixture', '{}')",
            "INSERT INTO checkpoints (run_id, event_sequence, step_number, run_revision, "
            "run_status, schema_version, state) VALUES (:other, 4, 1, 1, 'RUNNING', 1, '{}')",
            "INSERT INTO checkpoints (run_id, event_sequence, step_number, run_revision, "
            "run_status, schema_version, state) VALUES (:id, 3, 1, 1, 'RUNNING', 1, '{}')",
        ]
        for sql in bad_statements:
            with pytest.raises(IntegrityError):
                async with session.begin_nested():
                    await session.execute(text(sql), {"id": run.id, "other": other.id})
        assert await history.latest_checkpoint(run.id) == checkpoint
        await RunRepository(session).transition(run.id, RunStatus.SUCCEEDED, expected_revision=1)
        with pytest.raises(InvalidTransition):
            await history.record_step(
                run.id,
                kind="fixture",
                details={},
                state={},
                expected_revision=2,
                expected_sequence=5,
            )


async def test_upgrade_existing_runs_and_downgrade_preserves_phase1a(
    empty_database: AsyncEngine,
) -> None:
    async with empty_database.begin() as connection:
        await connection.run_sync(lambda conn: command.upgrade(migration_config(conn), "0001"))
    # Use the Phase 1A-compatible repository calls before installing the new schema.
    _, run = await seed(empty_database)
    async with async_sessionmaker(empty_database).begin() as session:
        await RunRepository(session).transition(run.id, RunStatus.RUNNING, expected_revision=0)
    async with empty_database.begin() as connection:
        await connection.run_sync(lambda conn: command.upgrade(migration_config(conn), "head"))
    async with async_sessionmaker(empty_database).begin() as session:
        history = HistoryRepository(session)
        events = await history.events(run.id)
        assert len(events) == 1 and events[0].kind == "run.snapshot"
        assert events[0].payload["history_complete"] is False
        assert events[0].payload["status"] == "RUNNING" and events[0].run_revision == 1
        await history.record_step(
            run.id,
            kind="fixture",
            details={},
            state={},
            expected_revision=1,
            expected_sequence=1,
        )
    async with empty_database.begin() as connection:
        await connection.run_sync(lambda conn: command.downgrade(migration_config(conn), "0001"))
        assert (
            await connection.scalar(text("SELECT status FROM runs WHERE id=:id"), {"id": run.id})
            == "RUNNING"
        )
        await connection.run_sync(lambda conn: command.upgrade(migration_config(conn), "head"))
        await connection.run_sync(lambda conn: command.check(migration_config(conn)))
    async with async_sessionmaker(empty_database).begin() as session:
        history = HistoryRepository(session)
        assert await history.latest_checkpoint(run.id) is None
        assert [e.kind for e in await history.events(run.id)] == ["run.snapshot"]
