import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from alembic import command
from conftest import migration_config
from runveil_core.agents import AgentVersion
from runveil_core.errors import InvalidTransition, NotFound, RevisionConflict
from runveil_core.runs import Run, RunStatus
from runveil_persistence.database import create_engine
from runveil_persistence.models import Base
from runveil_persistence.repositories import AgentRepository, RunRepository
from sqlalchemy import CheckConstraint, Connection, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def check_constraint_names(connection: Connection, table_name: str) -> set[str]:
    return {
        check["name"]
        for check in inspect(connection).get_check_constraints(table_name)
        if check["name"] is not None
    }


async def seed(database: AsyncEngine) -> tuple[AgentVersion, Run]:
    async with async_sessionmaker(database).begin() as session:
        agents = AgentRepository(session)
        agent = await agents.create("Test agent")
        version = await agents.create_version(agent.id, {"instructions": "Fixture only"})
        run = await RunRepository(session).create(version.id)
    return version, run


async def test_migration_round_trip_and_metadata(empty_database: AsyncEngine) -> None:
    async with empty_database.begin() as connection:
        await connection.run_sync(lambda conn: command.upgrade(migration_config(conn), "0003"))
    old_version, old_run = await seed(empty_database)
    _, enrolled_run = await seed(empty_database)
    async with empty_database.begin() as connection:
        await connection.run_sync(lambda conn: command.upgrade(migration_config(conn), "0004"))
        await connection.execute(
            text(
                "INSERT INTO worker_jobs (run_id, task, profile) "
                "VALUES (:id, 'Public task', 'fixture-v1')"
            ),
            {"id": enrolled_run.id},
        )
    async with empty_database.begin() as connection:
        await connection.run_sync(lambda conn: command.upgrade(migration_config(conn), "0005"))
        original_eligibility = await connection.scalar(text("SELECT available_at FROM worker_jobs"))
    async with empty_database.begin() as connection:
        await connection.run_sync(lambda conn: command.upgrade(migration_config(conn), "head"))
        await connection.run_sync(lambda conn: command.check(migration_config(conn)))
        tables = await connection.run_sync(lambda conn: inspect(conn).get_table_names())
        assert set(tables) == {
            "alembic_version",
            "agent_definitions",
            "agent_versions",
            "runs",
            "run_steps",
            "execution_events",
            "checkpoints",
            "model_invocations",
            "tool_calls",
            "worker_jobs",
            "worker_outbox",
        }
        assert await connection.scalar(text("SELECT count(*) FROM worker_jobs")) == 1
        assert (
            await connection.scalar(text("SELECT available_at FROM worker_jobs"))
            == original_eligibility
        )
        assert (
            await connection.scalar(
                text(
                    "SELECT available_at <= clock_timestamp() AND task='Public task' "
                    "AND profile='fixture-v1' AND token IS NULL AND deadline_at IS NULL "
                    "FROM worker_jobs WHERE run_id=:id"
                ),
                {"id": enrolled_run.id},
            )
            is True
        )
        for table in Base.metadata.sorted_tables:
            checks = await connection.run_sync(check_constraint_names, table.name)
            assert checks == {
                str(constraint.name)
                for constraint in table.constraints
                if isinstance(constraint, CheckConstraint)
            }

    async with async_sessionmaker(empty_database).begin() as session:
        assert await RunRepository(session).get(old_run.id) == old_run
        assert await AgentRepository(session).get_version(old_version.id) == old_version
    await seed(empty_database)
    async with empty_database.begin() as connection:
        await connection.run_sync(lambda conn: command.downgrade(migration_config(conn), "base"))
        tables = await connection.run_sync(lambda conn: inspect(conn).get_table_names())
        assert tables == ["alembic_version"]
        assert (
            await connection.scalar(
                text(
                    "SELECT count(*) FROM pg_proc WHERE proname IN "
                    "('guard_run_lifecycle', 'reject_agent_version_mutation')"
                )
            )
            == 0
        )
        await connection.run_sync(lambda conn: command.upgrade(migration_config(conn), "head"))
        await connection.run_sync(lambda conn: command.check(migration_config(conn)))
    await seed(empty_database)


async def test_persisted_snapshots_survive_new_connections(database: AsyncEngine) -> None:
    version, run = await seed(database)
    second_engine = create_engine(database.url)
    try:
        async with async_sessionmaker(second_engine).begin() as session:
            agents = AgentRepository(session)
            assert (await agents.get(version.agent_id)).name == "Test agent"
            assert await agents.get_version(version.id) == version
            stored = await RunRepository(session).get(run.id)
            assert stored == run
            assert stored.created_at.utcoffset() is not None
            next_version = await agents.create_version(
                version.agent_id, {"instructions": "Changed"}
            )
            assert next_version.number == 2
            assert stored.agent_version_id == version.id
            copy = version.configuration
            copy["instructions"] = "Modified"
            assert (await agents.get_version(version.id)).configuration == {
                "instructions": "Fixture only"
            }
    finally:
        await second_engine.dispose()


async def test_transaction_rollback_is_owned_by_caller(database: AsyncEngine) -> None:
    factory = async_sessionmaker(database)
    async with factory() as session:
        await session.begin()
        agent = await AgentRepository(session).create("Rolled back")
        version = await AgentRepository(session).create_version(agent.id, {})
        run = await RunRepository(session).create(version.id)
        await session.rollback()
    async with factory.begin() as session:
        with pytest.raises(NotFound):
            await AgentRepository(session).get(agent.id)
        with pytest.raises(NotFound):
            await AgentRepository(session).get_version(version.id)
        with pytest.raises(NotFound):
            await RunRepository(session).get(run.id)


async def test_missing_references_and_entities(database: AsyncEngine) -> None:
    async with async_sessionmaker(database).begin() as session:
        agents, runs = AgentRepository(session), RunRepository(session)
        with pytest.raises(NotFound):
            await agents.create_version(uuid4(), {})
        with pytest.raises(NotFound):
            await runs.create(uuid4())
        with pytest.raises(NotFound):
            await runs.transition(uuid4(), RunStatus.RUNNING, expected_revision=0)
        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                await session.execute(
                    text("INSERT INTO runs (id, agent_version_id) VALUES (:id, :version)"),
                    {"id": uuid4(), "version": uuid4()},
                )


async def test_versions_reject_sql_update_delete_and_duplicate_numbers(
    database: AsyncEngine,
) -> None:
    version, _ = await seed(database)
    async with database.begin() as connection:
        for sql in [
            "UPDATE agent_versions SET configuration = '{}'::jsonb WHERE id=:id",
            "DELETE FROM agent_versions WHERE id=:id",
            "UPDATE agent_versions SET number=9 WHERE id=:id",
        ]:
            with pytest.raises(IntegrityError, match="immutable"):
                async with connection.begin_nested():
                    await connection.execute(text(sql), {"id": version.id})
        with pytest.raises(IntegrityError):
            async with connection.begin_nested():
                await connection.execute(
                    text(
                        "INSERT INTO agent_versions (id, agent_id, number, configuration) "
                        "VALUES (:id, :agent, 1, '{}'::jsonb)"
                    ),
                    {"id": uuid4(), "agent": version.agent_id},
                )
        with pytest.raises(IntegrityError):
            async with connection.begin_nested():
                await connection.execute(
                    text("DELETE FROM agent_definitions WHERE id=:id"), {"id": version.agent_id}
                )


async def test_concurrent_version_allocation(database: AsyncEngine) -> None:
    version, _ = await seed(database)

    async def append() -> int:
        async with async_sessionmaker(database).begin() as session:
            return (await AgentRepository(session).create_version(version.agent_id, {})).number

    assert sorted(await asyncio.wait_for(asyncio.gather(append(), append()), timeout=10)) == [2, 3]


async def test_concurrent_transition_allows_one_writer(database: AsyncEngine) -> None:
    _, run = await seed(database)

    async def start() -> Run | RevisionConflict:
        try:
            async with async_sessionmaker(database).begin() as session:
                return await RunRepository(session).transition(
                    run.id, RunStatus.RUNNING, expected_revision=0
                )
        except RevisionConflict as error:
            return error

    results = await asyncio.wait_for(asyncio.gather(start(), start()), timeout=10)
    assert sum(isinstance(result, Run) for result in results) == 1
    assert sum(isinstance(result, RevisionConflict) for result in results) == 1
    async with async_sessionmaker(database).begin() as session:
        stored = await RunRepository(session).get(run.id)
        assert stored.status == RunStatus.RUNNING and stored.revision == 1


async def test_transition_validation_timestamps_and_rollback(database: AsyncEngine) -> None:
    _, run = await seed(database)
    factory = async_sessionmaker(database)
    async with factory.begin() as session:
        repo = RunRepository(session)
        with pytest.raises(InvalidTransition):
            await repo.transition(run.id, RunStatus.SUCCEEDED, expected_revision=0)
        started = await repo.transition(run.id, RunStatus.RUNNING, expected_revision=0)
        waiting = await repo.transition(run.id, RunStatus.WAITING_FOR_APPROVAL, expected_revision=1)
        resumed = await repo.transition(run.id, RunStatus.RUNNING, expected_revision=2)
        assert resumed.started_at == started.started_at
        assert (
            run.created_at
            <= started.state_changed_at
            <= waiting.state_changed_at
            <= resumed.state_changed_at
        )
    async with factory() as session:
        finished = await RunRepository(session).transition(
            run.id, RunStatus.SUCCEEDED, expected_revision=3
        )
        assert finished.finished_at == finished.state_changed_at
        await session.rollback()
    async with factory.begin() as session:
        assert await RunRepository(session).get(run.id) == resumed
        with pytest.raises(RevisionConflict):
            await RunRepository(session).transition(
                run.id, RunStatus.CANCELLED, expected_revision=0
            )


async def test_database_transition_matrix(database: AsyncEngine) -> None:
    # Deliberately independent of the implementation's Python transition table.
    allowed = {
        "QUEUED": {"RUNNING", "CANCELLED"},
        "RUNNING": {"WAITING_FOR_APPROVAL", "RETRYING", "SUCCEEDED", "FAILED", "CANCELLED"},
        "WAITING_FOR_APPROVAL": {"RUNNING", "FAILED", "CANCELLED"},
        "RETRYING": {"RUNNING", "FAILED", "CANCELLED"},
        "SUCCEEDED": set(),
        "FAILED": set(),
        "CANCELLED": set(),
    }
    version, _ = await seed(database)
    for source in RunStatus:
        for target in RunStatus:
            async with async_sessionmaker(database).begin() as session:
                repo = RunRepository(session)
                run = await repo.create(version.id)
                if source != RunStatus.QUEUED:
                    run = await repo.transition(run.id, RunStatus.RUNNING, expected_revision=0)
                    if source != RunStatus.RUNNING:
                        run = await repo.transition(run.id, source, expected_revision=1)
                params = {"id": run.id, "status": target.value, "at": datetime.now(UTC)}
                sql = text("""UPDATE runs SET status=CAST(:status AS varchar), revision=revision+1,
                    state_changed_at=:at,
                    started_at=CASE WHEN started_at IS NULL AND CAST(:status AS varchar)='RUNNING'
                        THEN :at ELSE started_at END,
                    finished_at=CASE WHEN CAST(:status AS varchar)
                        IN ('SUCCEEDED','FAILED','CANCELLED')
                        THEN :at ELSE NULL END
                    WHERE id=:id""")
                if target.value in allowed[source.value]:
                    await session.execute(sql, params)
                    assert (await repo.get(run.id)).status == target
                    assert (
                        await session.scalar(
                            text(
                                "SELECT payload->>'status' FROM execution_events "
                                "WHERE run_id=:id ORDER BY sequence DESC LIMIT 1"
                            ),
                            {"id": run.id},
                        )
                        == target.value
                    )
                else:
                    with pytest.raises(IntegrityError, match="Invalid run transition"):
                        async with session.begin_nested():
                            await session.execute(sql, params)
                    assert (await repo.get(run.id)).status == source


async def test_database_rejects_forged_identity_revision_and_timestamps(
    database: AsyncEngine,
) -> None:
    version, run = await seed(database)
    async with database.begin() as connection:
        with pytest.raises(IntegrityError):
            async with connection.begin_nested():
                await connection.execute(
                    text(
                        "INSERT INTO runs (id, agent_version_id, status) "
                        "VALUES (:id, :version, 'RUNNING')"
                    ),
                    {"id": uuid4(), "version": version.id},
                )
        changes = [
            ("revision", "9", "revision"),
            ("id", ":other", "identity"),
            ("created_at", "created_at-interval '1 day'", "identity"),
            ("state_changed_at", "created_at-interval '1 day'", "transition time"),
            ("started_at", "created_at-interval '1 day'", "Start time"),
        ]
        for field, expression, message in changes:
            assignments = {
                "status": "'RUNNING'",
                "revision": "revision+1",
                "state_changed_at": ":at",
                "started_at": ":at",
            }
            assignments[field] = expression
            clause = ", ".join(f"{key}={value}" for key, value in assignments.items())
            with pytest.raises(IntegrityError, match=message):
                async with connection.begin_nested():
                    await connection.execute(
                        text(f"UPDATE runs SET {clause} WHERE id=:id"),
                        {"id": run.id, "other": uuid4(), "at": datetime.now(UTC)},
                    )
    async with async_sessionmaker(database).begin() as session:
        await RunRepository(session).transition(run.id, RunStatus.RUNNING, expected_revision=0)
    async with database.begin() as connection:
        with pytest.raises(IntegrityError, match="First start time"):
            async with connection.begin_nested():
                await connection.execute(
                    text(
                        "UPDATE runs SET status='RETRYING', revision=revision+1, "
                        "state_changed_at=:at, started_at=:at WHERE id=:id"
                    ),
                    {"id": run.id, "at": datetime.now(UTC)},
                )
