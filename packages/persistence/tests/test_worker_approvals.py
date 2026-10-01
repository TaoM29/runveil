"""Approval suspension uses existing claims, checkpoints and immutable workspace bindings."""

import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal
from uuid import UUID

import pytest
from runveil_core.agents import JsonValue
from runveil_core.approvals import PROPOSAL_TOOL, REVIEW_PROFILE, ApprovalRequest
from runveil_core.errors import InvalidTransition, NotFound, RevisionConflict
from runveil_core.runs import RunStatus
from runveil_core.runtime import Cursor, Pending, RuntimeConfig, RuntimeState, execute
from runveil_core.tools import ToolRegistry
from runveil_persistence import execution, jobs
from runveil_persistence.approvals import ApprovalRepository
from runveil_persistence.database import create_engine
from runveil_persistence.execution import PostgresExecutionStore
from runveil_persistence.history import HistoryRepository
from runveil_persistence.jobs import OwnershipLost, claim_next
from runveil_persistence.models import ApprovalRow, JobRow, ModelInvocationRow, ToolCallRow
from runveil_persistence.repositories import RunRepository
from runveil_persistence.worker_approvals import pause_review, resolve_worker_review
from runveil_tools import review as review_module
from runveil_tools.repository import RepositoryAccess, RepositoryTools
from runveil_tools.review import proposal_binding
from runveil_worker.review_worker import (
    POLICY,
    ReviewProvider,
    review_configuration,
    submit_review,
    work_review_once,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from test_worker import expire

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]
ACCESS = RepositoryAccess(files=("a.txt",))


async def test_approved_restart_rechecks_workspace_and_preserves_budgets(
    database: AsyncEngine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "a.txt"
    path.write_text("public fixture")
    sessions = async_sessionmaker(database)
    run_id = await submit_review(sessions, tmp_path, ACCESS)
    state = await work_review_once(sessions, tmp_path, ACCESS, run_id=run_id)
    assert state is not None and state.approval_id is not None and not state.approval_resolved
    assert state.steps_used == 4 and state.tokens.attempts == 2
    async with sessions.begin() as session:
        request = await ApprovalRepository(session).get(run_id)
        job = await session.get(JobRow, run_id)
        assert job is not None and job.token is None and job.expires_at is None
        deadline = job.deadline_at
        assert (await RunRepository(session).get(run_id)).status == RunStatus.WAITING_FOR_APPROVAL
        with pytest.raises(ValueError, match="unenrolled"):
            await ApprovalRepository(session).resolve(
                run_id, decision="APPROVED", expected_revision=2, expected_digest=request.digest
            )
    assert await work_review_once(sessions, tmp_path, ACCESS, run_id=run_id) is None
    restarted = create_engine(database.url)
    try:
        fresh = async_sessionmaker(restarted)
        async with fresh.begin() as session:
            with pytest.raises(RevisionConflict):
                await resolve_worker_review(
                    session,
                    run_id,
                    decision="APPROVED",
                    expected_revision=2,
                    expected_digest="0" * 64,
                )
            await resolve_worker_review(
                session,
                run_id,
                decision="APPROVED",
                expected_revision=2,
                expected_digest=request.digest,
            )
        path.write_text("changed after approval")
        async with fresh.begin() as session:
            before = await HistoryRepository(session).events(run_id)
        with pytest.raises(ValueError, match="worker profile"):
            await work_review_once(fresh, tmp_path, ACCESS, run_id=run_id)
        async with fresh.begin() as session:
            assert await HistoryRepository(session).events(run_id) == before
        path.write_text("public fixture")
        await expire(fresh, run_id)
        with monkeypatch.context() as changed:
            changed.setattr(review_module, "_IMPLEMENTATION_DIGEST", "0" * 64)
            with pytest.raises(ValueError, match="worker profile"):
                await work_review_once(fresh, tmp_path, ACCESS, run_id=run_id)
        async with fresh.begin() as session:
            assert await HistoryRepository(session).events(run_id) == before
        await expire(fresh, run_id)
        finished = await work_review_once(fresh, tmp_path, ACCESS, run_id=run_id)
        assert finished is not None and finished.final_result is not None
        assert finished.approval_id == state.approval_id and finished.approval_resolved
        assert finished.steps_used == 5 and finished.tokens.attempts == 3
        async with fresh.begin() as session:
            job = await session.get(JobRow, run_id)
            assert job is not None and job.deadline_at == deadline
            assert await session.scalar(select(func.count()).select_from(ApprovalRow)) == 1
            assert await session.scalar(select(func.count()).select_from(ToolCallRow)) == 2
        assert await work_review_once(fresh, tmp_path, ACCESS, run_id=run_id) is None
        assert path.read_text() == "public fixture"
    finally:
        await restarted.dispose()


async def test_resolution_rollback_race_rejection_and_cancellation(
    database: AsyncEngine, tmp_path: Path
) -> None:
    (tmp_path / "a.txt").write_text("public fixture")
    sessions = async_sessionmaker(database)
    run_id = await submit_review(sessions, tmp_path, ACCESS)
    await work_review_once(sessions, tmp_path, ACCESS, run_id=run_id)
    async with sessions.begin() as session:
        request = await ApprovalRepository(session).get(run_id)
    async with sessions() as session:
        await resolve_worker_review(
            session,
            run_id,
            decision="APPROVED",
            expected_revision=2,
            expected_digest=request.digest,
        )
        await session.rollback()
    async with sessions.begin() as session:
        assert (await ApprovalRepository(session).get(run_id)).status == "PENDING"
        assert (await RunRepository(session).get(run_id)).status == RunStatus.WAITING_FOR_APPROVAL

    async def reject() -> ApprovalRequest | RevisionConflict:
        try:
            async with sessions.begin() as session:
                return await resolve_worker_review(
                    session,
                    run_id,
                    decision="REJECTED",
                    expected_revision=2,
                    expected_digest=request.digest,
                )
        except RevisionConflict as exc:
            return exc

    results = await asyncio.wait_for(asyncio.gather(reject(), reject()), 10)
    assert sum(isinstance(result, ApprovalRequest) for result in results) == 1
    assert sum(isinstance(result, RevisionConflict) for result in results) == 1
    assert await work_review_once(sessions, tmp_path, ACCESS, run_id=run_id) is None
    async with sessions.begin() as session:
        assert (await RunRepository(session).get(run_id)).status == RunStatus.FAILED
    cancelled = await submit_review(sessions, tmp_path, ACCESS)
    await work_review_once(sessions, tmp_path, ACCESS, run_id=cancelled)
    async with sessions.begin() as session:
        request = await ApprovalRepository(session).get(cancelled)
        await RunRepository(session).transition(cancelled, RunStatus.CANCELLED, expected_revision=2)
        with pytest.raises(InvalidTransition):
            await resolve_worker_review(
                session,
                cancelled,
                decision="APPROVED",
                expected_revision=3,
                expected_digest=request.digest,
            )
    assert (tmp_path / "a.txt").read_text() == "public fixture"


@pytest.mark.parametrize("cut", ["intent", "paused", "rollback"])
async def test_crash_and_pause_atomicity(
    database: AsyncEngine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cut: str
) -> None:
    (tmp_path / "a.txt").write_text("public fixture")
    sessions = async_sessionmaker(database)
    run_id = await submit_review(sessions, tmp_path, ACCESS)
    claim = await claim_next(sessions, profile=REVIEW_PROFILE, run_id=run_id)
    assert claim is not None

    class Cut(PostgresExecutionStore):
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
            if cut == "intent" and tool_name == PROPOSAL_TOOL:
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
            if cut == "paused" and state.approval_id is not None:
                raise asyncio.CancelledError
            return cursor

    real_pause = pause_review

    async def rollback_pause(session: AsyncSession, row: ApprovalRow, revision: int) -> None:
        await real_pause(session, row, revision)
        raise asyncio.CancelledError

    if cut == "rollback":
        monkeypatch.setattr(execution, "pause_review", rollback_pause)
    with RepositoryTools(tmp_path, access=ACCESS, snapshot=True) as repo:
        config = review_configuration(repo)
        with pytest.raises(asyncio.CancelledError):
            await execute(
                run_id,
                claim.task,
                provider_name=config.provider,
                provider=ReviewProvider("a.txt"),
                tools=ToolRegistry((*repo.bindings(), proposal_binding(repo))),
                tool_policy=POLICY,
                store=Cut(sessions, claim=claim, expected_config=config),
            )
    if cut == "paused":
        assert await claim_next(sessions, profile=REVIEW_PROFILE, run_id=run_id) is None
        async with sessions.begin() as session:
            with pytest.raises(OwnershipLost):
                await jobs.fence(session, run_id, claim)
            assert (await ApprovalRepository(session).get(run_id)).status == "PENDING"
    else:
        async with sessions.begin() as session:
            with pytest.raises(NotFound):
                await ApprovalRepository(session).get(run_id)
        assert await claim_next(sessions, profile=REVIEW_PROFILE, run_id=run_id) is None
        await expire(sessions, run_id)
        result = await work_review_once(sessions, tmp_path, ACCESS, run_id=run_id)
        assert result is not None and result.error_code == "execution_interrupted"
        async with sessions.begin() as session:
            assert await session.scalar(select(func.count()).select_from(ToolCallRow)) == 2
    assert (tmp_path / "a.txt").read_text() == "public fixture"


async def test_approval_wait_does_not_extend_deadline(
    database: AsyncEngine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "a.txt").write_text("public fixture")
    sessions = async_sessionmaker(database)
    run_id = await submit_review(sessions, tmp_path, ACCESS)
    await work_review_once(sessions, tmp_path, ACCESS, run_id=run_id)
    async with sessions.begin() as session:
        request = await ApprovalRepository(session).get(run_id)
        job = await session.get(JobRow, run_id)
        assert job is not None and job.deadline_at is not None
        after_deadline = job.deadline_at + timedelta(seconds=1)

    async def now(session: AsyncSession) -> datetime:
        return after_deadline

    monkeypatch.setattr(jobs, "database_now", now)
    monkeypatch.setattr(execution, "database_now", now)
    assert await claim_next(sessions, profile=REVIEW_PROFILE, run_id=run_id) is None
    async with sessions.begin() as session:
        await resolve_worker_review(
            session,
            run_id,
            decision="APPROVED",
            expected_revision=2,
            expected_digest=request.digest,
        )
    result = await work_review_once(sessions, tmp_path, ACCESS, run_id=run_id)
    assert result is not None and result.error_code == "elapsed_time_exceeded"
    async with sessions.begin() as session:
        assert await session.scalar(select(func.count()).select_from(ModelInvocationRow)) == 2
        assert (await RunRepository(session).get(run_id)).status == RunStatus.FAILED
