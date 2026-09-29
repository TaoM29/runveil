"""Pinned repository recovery rejects binding drift before execution."""

import asyncio
from pathlib import Path

import pytest
from runveil_core.agents import JsonValue
from runveil_core.runtime import Cursor, Pending, RuntimeState, execute
from runveil_core.tools import ToolRegistry
from runveil_persistence.database import create_engine
from runveil_persistence.execution import PostgresExecutionStore, load_runtime_state
from runveil_persistence.history import HistoryRepository
from runveil_persistence.jobs import claim_next
from runveil_persistence.models import ModelInvocationRow, ToolCallRow
from runveil_tools import repository as repository_module
from runveil_tools.repository import RepositoryAccess, RepositoryTools
from runveil_worker.repository_worker import (
    POLICY,
    PROFILE,
    RepositoryProvider,
    repository_configuration,
    submit_repository,
    work_repository_once,
)
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.mark.parametrize(
    "change", ["root", "replacement", "allowlist", "content", "implementation"]
)
async def test_repository_recovery_refuses_drift(
    database: AsyncEngine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    (checkout / "a.txt").write_text("public fixture", encoding="utf-8")
    (checkout / "b.txt").write_text("other public fixture", encoding="utf-8")
    access = RepositoryAccess(files=("a.txt",))
    sessions = async_sessionmaker(database)
    run_id = await submit_repository(sessions, checkout, access)
    claim = await claim_next(sessions, profile=PROFILE, run_id=run_id)
    assert claim is not None
    with RepositoryTools(checkout, access=access, snapshot=True) as repository:
        config = repository_configuration(repository)
        with pytest.raises(ValueError, match="verified binding"):
            await PostgresExecutionStore(sessions, claim=claim).start(
                run_id, claim.task, config.provider
            )
        await PostgresExecutionStore(sessions, claim=claim, expected_config=config).start(
            run_id, claim.task, config.provider
        )
    async with sessions.begin() as session:
        before = await HistoryRepository(session).events(run_id)
        state = await load_runtime_state(session, run_id)
        await session.execute(
            text(
                "UPDATE worker_jobs SET expires_at=clock_timestamp() "
                "- interval '1 second' WHERE run_id=:id"
            ),
            {"id": run_id},
        )
    root = checkout
    if change == "root":
        root = tmp_path / "replacement"
        root.mkdir()
        (root / "a.txt").write_text("public fixture", encoding="utf-8")
    elif change == "replacement":
        checkout.rename(tmp_path / "retired")
        checkout.mkdir()
        (checkout / "a.txt").write_text("public fixture", encoding="utf-8")
    elif change == "allowlist":
        access = RepositoryAccess(files=("a.txt", "b.txt"))
    elif change == "content":
        (checkout / "a.txt").write_text("different public fixture", encoding="utf-8")
    else:
        monkeypatch.setattr(repository_module, "_IMPLEMENTATION_DIGEST", "f" * 64)
    with pytest.raises(ValueError, match="worker profile"):
        await work_repository_once(sessions, root, access, run_id=run_id)
    async with sessions.begin() as session:
        assert await load_runtime_state(session, run_id) == state
        assert await HistoryRepository(session).events(run_id) == before
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ModelInvocationRow)
                .where(ModelInvocationRow.run_id == run_id)
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count()).select_from(ToolCallRow).where(ToolCallRow.run_id == run_id)
            )
            == 0
        )


@pytest.mark.parametrize("cut", [1, 2])
async def test_repository_clean_checkpoint_recovers_same_snapshot(
    database: AsyncEngine, tmp_path: Path, cut: int
) -> None:
    (tmp_path / "a.txt").write_text("public snapshot content", encoding="utf-8")
    access = RepositoryAccess(files=("a.txt",))
    sessions = async_sessionmaker(database)
    run_id = await submit_repository(sessions, tmp_path, access)
    claim = await claim_next(sessions, profile=PROFILE, run_id=run_id)
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

    with RepositoryTools(tmp_path, access=access, snapshot=True) as repository:
        config = repository_configuration(repository)
        with pytest.raises(asyncio.CancelledError):
            await execute(
                run_id,
                claim.task,
                provider_name=config.provider,
                provider=RepositoryProvider("a.txt"),
                tools=ToolRegistry(repository.bindings()),
                tool_policy=POLICY,
                store=Stop(sessions, claim=claim, expected_config=config),
            )
    async with sessions.begin() as session:
        await session.execute(
            text(
                "UPDATE worker_jobs SET expires_at=clock_timestamp() "
                "- interval '1 second' WHERE run_id=:id"
            ),
            {"id": run_id},
        )
    restarted = create_engine(database.url)
    try:
        outcome = await work_repository_once(
            async_sessionmaker(restarted), tmp_path, access, run_id=run_id
        )
    finally:
        await restarted.dispose()
    assert outcome is not None and outcome[1].final_result is not None
    assert outcome[1].steps_used == 3 and outcome[1].tokens.attempts == 2
    async with sessions.begin() as session:
        records = list(
            await session.scalars(select(ToolCallRow).where(ToolCallRow.run_id == run_id))
        )
        assert len(records) == 1 and records[0].result is not None
        assert records[0].result["content"] == "public snapshot content"
    assert await work_repository_once(sessions, tmp_path, access, run_id=run_id) is None
