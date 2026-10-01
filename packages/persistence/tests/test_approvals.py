import asyncio
from typing import Literal
from uuid import UUID

import pytest
from alembic import command
from conftest import migration_config
from runveil_core.approvals import REVIEW_CONFIGURATION, ApprovalRequest, PatchProposal
from runveil_core.errors import InvalidTransition, NotFound, RevisionConflict
from runveil_core.runs import RunStatus
from runveil_persistence.approvals import ApprovalRepository
from runveil_persistence.database import create_engine
from runveil_persistence.history import HistoryRepository
from runveil_persistence.jobs import claim_next, enroll
from runveil_persistence.repositories import AgentRepository, RunRepository
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from test_persistence import seed

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]
PROPOSAL = PatchProposal(path="example.txt", before="before\n", after="after\n")


async def review_run(database: AsyncEngine) -> UUID:
    async with async_sessionmaker(database).begin() as session:
        agents = AgentRepository(session)
        agent = await agents.create("Review fixture")
        version = await agents.create_version(agent.id, REVIEW_CONFIGURATION)
        return (await RunRepository(session).create(version.id)).id


async def test_pause_restart_approve_and_no_dispatch(database: AsyncEngine) -> None:
    run_id = await review_run(database)
    factory = async_sessionmaker(database)
    async with factory.begin() as session:
        request = await ApprovalRepository(session).request(run_id, PROPOSAL)
    assert await claim_next(factory, profile="patch-review-v1", run_id=run_id) is None
    restored_engine = create_engine(database.url)
    try:
        async with async_sessionmaker(restored_engine).begin() as session:
            approvals = ApprovalRepository(session)
            assert await approvals.get(run_id) == request
            run = await RunRepository(session).get(run_id)
            assert run.status == RunStatus.WAITING_FOR_APPROVAL and run.revision == 2
            with pytest.raises(RevisionConflict):
                await approvals.resolve(
                    run_id, decision="APPROVED", expected_revision=2, expected_digest="0" * 64
                )
            approved = await approvals.resolve(
                run_id, decision="APPROVED", expected_revision=2, expected_digest=request.digest
            )
            assert approved.status == "APPROVED" and approved.decided_at is not None
        async with factory.begin() as session:
            assert (await RunRepository(session).get(run_id)).status == RunStatus.SUCCEEDED
            history = HistoryRepository(session)
            checkpoint = await history.latest_checkpoint(run_id)
            assert checkpoint is not None
            assert checkpoint.state["patch_applied"] is False
            assert checkpoint.state["result"] == "approved"
            events = await history.events(run_id)
            assert [event.kind for event in events] == [
                "run.created",
                "run.transitioned",
                "approval.requested",
                "step.recorded",
                "checkpoint.created",
                "run.transitioned",
                "approval.approved",
                "run.transitioned",
                "step.recorded",
                "checkpoint.created",
                "run.transitioned",
            ]
            assert await session.scalar(text("SELECT count(*) FROM tool_calls")) == 0
            assert await session.scalar(text("SELECT count(*) FROM worker_jobs")) == 0
            with pytest.raises(RevisionConflict):
                await ApprovalRepository(session).resolve(
                    run_id,
                    decision="REJECTED",
                    expected_revision=2,
                    expected_digest=request.digest,
                )
    finally:
        await restored_engine.dispose()


async def test_rollback_reject_cancel_and_worker_boundary(database: AsyncEngine) -> None:
    run_id = await review_run(database)
    factory = async_sessionmaker(database)
    async with factory() as session:
        await ApprovalRepository(session).request(run_id, PROPOSAL)
        await session.rollback()
    async with factory.begin() as session:
        assert (await RunRepository(session).get(run_id)).status == RunStatus.QUEUED
        with pytest.raises(NotFound):
            await ApprovalRepository(session).get(run_id)
        assert len(await HistoryRepository(session).events(run_id)) == 1
        await ApprovalRepository(session).request(run_id, PROPOSAL)
    async with factory() as session:
        await ApprovalRepository(session).resolve(
            run_id,
            decision="APPROVED",
            expected_revision=2,
            expected_digest=PROPOSAL.digest,
        )
        await session.rollback()
    async with factory.begin() as session:
        approvals = ApprovalRepository(session)
        assert (await approvals.get(run_id)).status == "PENDING"
        await approvals.resolve(
            run_id, decision="REJECTED", expected_revision=2, expected_digest=PROPOSAL.digest
        )
        assert (await RunRepository(session).get(run_id)).status == RunStatus.FAILED
        assert [e.kind for e in await HistoryRepository(session).events(run_id)][-2:] == [
            "approval.rejected",
            "run.transitioned",
        ]
    cancelled = await review_run(database)
    enrolled = await review_run(database)
    _, ordinary = await seed(database)
    async with factory.begin() as session:
        approvals = ApprovalRepository(session)
        await approvals.request(cancelled, PROPOSAL)
        await RunRepository(session).transition(cancelled, RunStatus.CANCELLED, expected_revision=2)
        with pytest.raises(InvalidTransition):
            await approvals.resolve(
                cancelled, decision="APPROVED", expected_revision=3, expected_digest=PROPOSAL.digest
            )
        await enroll(session, enrolled, task="test", profile="fixture-v1")
        for blocked in (enrolled, ordinary.id):
            with pytest.raises(ValueError, match="dedicated, unenrolled"):
                await approvals.request(blocked, PROPOSAL)
            assert (await RunRepository(session).get(blocked)).status == RunStatus.QUEUED


async def test_competing_decisions_and_database_immutability(database: AsyncEngine) -> None:
    run_id = await review_run(database)
    factory = async_sessionmaker(database)
    async with factory.begin() as session:
        await ApprovalRepository(session).request(run_id, PROPOSAL)

    async def decide(
        decision: Literal["APPROVED", "REJECTED"],
    ) -> ApprovalRequest | RevisionConflict:
        try:
            async with factory.begin() as session:
                return await ApprovalRepository(session).resolve(
                    run_id,
                    decision=decision,
                    expected_revision=2,
                    expected_digest=PROPOSAL.digest,
                )
        except RevisionConflict as exc:
            return exc

    results = await asyncio.wait_for(asyncio.gather(decide("APPROVED"), decide("REJECTED")), 10)
    assert sum(isinstance(result, ApprovalRequest) for result in results) == 1
    assert sum(isinstance(result, RevisionConflict) for result in results) == 1
    async with factory.begin() as session:
        for sql in (
            "DELETE FROM approval_requests",
            "UPDATE approval_requests SET proposal = '{}'",
            "UPDATE approval_requests SET status = 'PENDING', decided_at = NULL",
        ):
            with pytest.raises(IntegrityError, match="immutable"):
                async with session.begin_nested():
                    await session.execute(text(sql))
        events = await HistoryRepository(session).events(run_id)
        assert (
            len(
                [
                    event
                    for event in events
                    if event.kind
                    in (
                        "approval.approved",
                        "approval.rejected",
                    )
                ]
            )
            == 1
        )


async def test_populated_upgrade_and_downgrade(empty_database: AsyncEngine) -> None:
    async with empty_database.begin() as connection:
        await connection.run_sync(lambda conn: command.upgrade(migration_config(conn), "0008"))
    _, prior = await seed(empty_database)
    async with empty_database.begin() as connection:
        await connection.run_sync(lambda conn: command.upgrade(migration_config(conn), "head"))
        await connection.run_sync(lambda conn: command.check(migration_config(conn)))
    run_id = await review_run(empty_database)
    async with async_sessionmaker(empty_database).begin() as session:
        await ApprovalRepository(session).request(run_id, PROPOSAL)
        assert (await RunRepository(session).get(prior.id)).status == RunStatus.QUEUED
        # Even a pending proposal cannot be swapped while deciding it.
        with pytest.raises(IntegrityError, match="immutable"):
            async with session.begin_nested():
                await session.execute(
                    text(
                        "UPDATE approval_requests SET proposal = '{}', status = 'APPROVED', "
                        "decided_at = clock_timestamp()"
                    )
                )
    async with empty_database.begin() as connection:
        await connection.run_sync(lambda conn: command.downgrade(migration_config(conn), "0008"))
        await connection.run_sync(lambda conn: command.upgrade(migration_config(conn), "head"))
        await connection.run_sync(lambda conn: command.check(migration_config(conn)))
