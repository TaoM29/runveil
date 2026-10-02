"""Real stdio recovery through PostgreSQL claims, checkpoints and admission fences."""

import asyncio
import json
import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal
from uuid import UUID

import pytest
from mcp import ClientSession, StdioServerParameters, types
from runveil_core.agents import JsonValue
from runveil_core.mcp import MCP_PROFILE
from runveil_core.runtime import Cursor, Pending, RuntimeConfig, RuntimeState
from runveil_core.tools import ToolError
from runveil_persistence.execution import (
    ConfigurationRejected,
    PostgresExecutionStore,
    load_runtime_state,
)
from runveil_persistence.history import HistoryRepository
from runveil_persistence.jobs import OwnershipLost, claim_next
from runveil_persistence.models import ModelInvocationRow, ToolCallRow
from runveil_persistence.repositories import RunRepository
from runveil_persistence.traces import read_trace
from runveil_tools import mcp as adapter
from runveil_tools.mcp_execution import PinnedMcpFixture
from runveil_worker import mcp_worker as worker
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from test_sandbox_worker import expire

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_grant_identity_and_store_guards_precede_execution(
    database: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    sessions = async_sessionmaker(database)
    run_id = await worker.submit_mcp(sessions)
    async with sessions() as session:
        before = await HistoryRepository(session).events(run_id)
    with pytest.raises(ToolError, match="tool_permission_denied"):
        await worker.work_mcp_once(sessions, run_id=run_id)
    await expire(sessions, run_id)
    claim = await claim_next(sessions, profile=MCP_PROFILE, run_id=run_id)
    assert claim is not None
    config = worker.bound_configuration(PinnedMcpFixture())
    async with sessions.begin() as session:
        original_run = await RunRepository(session).get(run_id)
        unclaimed = await RunRepository(session).create(original_run.agent_version_id)
    with pytest.raises(ConfigurationRejected, match="dedicated profile"):
        await PostgresExecutionStore(sessions, expected_config=config).start(
            unclaimed.id, claim.task, config.provider
        )
    with pytest.raises(ConfigurationRejected, match="verified binding"):
        await PostgresExecutionStore(sessions, claim=claim).start(
            run_id, claim.task, config.provider
        )
    for update in (
        {"schema_version": 8},
        {"mcp": None},
        {"tool_policy": {"permissions": ["write"]}},
    ):
        with pytest.raises(ValueError):
            RuntimeConfig.model_validate_json(json.dumps(config.model_dump(mode="json") | update))
    await PostgresExecutionStore(sessions, claim=claim, expected_config=config).start(
        run_id, claim.task, config.provider
    )
    async with sessions() as session:
        before = await HistoryRepository(session).events(run_id)
    original = PinnedMcpFixture
    for field in (
        "server_digest",
        "interpreter_digest",
        "contract_digest",
        "implementation_digest",
    ):
        await expire(sessions, run_id)

        def drift(field: str = field) -> PinnedMcpFixture:
            binding = original()
            binding.identity = binding.identity.model_copy(update={field: "f" * 64})
            return binding

        with monkeypatch.context() as patch:
            patch.setattr(worker, "PinnedMcpFixture", drift)
            with pytest.raises(ConfigurationRejected, match="worker profile"):
                await worker.work_mcp_once(sessions, run_id=run_id, allow_read=True)
    async with sessions() as session:
        assert await HistoryRepository(session).events(run_id) == before
        assert await session.scalar(select(ModelInvocationRow.id)) is None
        assert await session.scalar(select(ToolCallRow.id)) is None
    await expire(sessions, run_id)
    state = await worker.work_mcp_once(sessions, run_id=run_id, allow_read=True)
    assert state is not None and state.final_result is not None and state.steps_used == 3
    async with sessions() as session:
        trace = await read_trace(session, run_id)
        assert trace.tool_calls == 1 and trace.approval is None
        assert trace.checkpoint is not None and trace.checkpoint.schema_version == 17
        assert trace.checkpoint.tokens == state.tokens and trace.checkpoint.cost == state.cost
    assert await worker.work_mcp_once(sessions, run_id=run_id) is None


@pytest.mark.parametrize(
    "cut", ["model_checkpoint", "tool_checkpoint", "model_intent", "tool_intent", "response"]
)
async def test_clean_recovery_and_uncertain_intent_without_server_replay(
    database: AsyncEngine, monkeypatch: pytest.MonkeyPatch, cut: str
) -> None:
    sessions = async_sessionmaker(database)
    run_id = await worker.submit_mcp(sessions)

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
            if cut == kind + "_intent":
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
            if cut == "response" and pending.kind == "tool":
                assert result == {"project": "Runveil", "fixture_version": 1}
                raise asyncio.CancelledError
            cursor = await super().complete(pending, state, result=result, error_code=error_code)
            if cut == pending.kind + "_checkpoint":
                raise asyncio.CancelledError
            return cursor

    with monkeypatch.context() as patch:
        patch.setattr(worker, "PostgresExecutionStore", Stop)
        with pytest.raises(asyncio.CancelledError):
            await worker.work_mcp_once(sessions, run_id=run_id, allow_read=True)
    assert await worker.work_mcp_once(sessions, run_id=run_id, allow_read=True) is None
    await expire(sessions, run_id)
    interrupted = cut in ("model_intent", "tool_intent", "response")
    if interrupted:

        def forbidden() -> PinnedMcpFixture:
            raise AssertionError("Uncertain intent must not construct a server binding")

        with monkeypatch.context() as patch:
            patch.setattr(worker, "PinnedMcpFixture", forbidden)
            state = await worker.work_mcp_once(sessions, run_id=run_id)
        assert state is not None and state.error_code == "execution_interrupted"
    else:
        child = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "runveil_worker.mcp_worker",
            "work",
            "--run-id",
            str(run_id),
            "--allow-read",
            env=os.environ
            | {
                "DATABASE_URL": database.url.render_as_string(hide_password=False),
                "RUNVEIL_TELEMETRY": "json",
            },
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(child.communicate(), 30)
            assert child.returncode == 0, stdout.decode()
            assert json.loads(stdout)["error_code"] is None
            spans = [json.loads(line) for line in stderr.splitlines()]
            dispatches = [span for span in spans if span["name"] == "tool.dispatch"]
            assert len(dispatches) == int(cut == "model_checkpoint")
            async with sessions() as session:
                state = await load_runtime_state(session, run_id)
                assert state is not None and state.final_result is not None
                assert state.steps_used == 3 and state.tokens.attempts == 2
                if dispatches:
                    call = (await session.scalars(select(ToolCallRow))).one()
                    assert dispatches[0]["attributes"]["invocation_id"] == str(call.id)
        finally:
            if child.returncode is None:
                child.kill()
            await child.wait()
    async with sessions() as session:
        calls = list(await session.scalars(select(ToolCallRow)))
        assert len(calls) == int(cut != "model_intent")
        if calls:
            assert calls[0].error_code == ("execution_interrupted" if interrupted else None)
            assert calls[0].model_invocation_id is not None
        assert await load_runtime_state(session, run_id) == state
    assert await worker.work_mcp_once(sessions, run_id=run_id) is None


@pytest.mark.parametrize("lose_at", ["discovery", "response"])
async def test_admission_fence_and_late_outcome_refusal(
    database: AsyncEngine, monkeypatch: pytest.MonkeyPatch, lose_at: str
) -> None:
    sessions = async_sessionmaker(database)
    run_id = await worker.submit_mcp(sessions)
    connect = adapter.connect_read_tools
    calls = 0

    @asynccontextmanager
    async def observed(server: StdioServerParameters) -> AsyncIterator[adapter.McpReadTools]:
        async with sessions() as session:
            call = (await session.scalars(select(ToolCallRow))).one()
            assert call.status == "REQUESTED"
        async with connect(server) as connection:
            if lose_at == "discovery":
                await expire(sessions, run_id)
            yield connection

    # Count actual SDK calls, not durable intents, and expire after a remote result.
    original_call = ClientSession.call_tool

    async def call_tool(
        self: ClientSession,
        name: str,
        arguments: dict[str, object] | None = None,
    ) -> types.CallToolResult:
        nonlocal calls
        result = await original_call(self, name, arguments=arguments)
        calls += 1
        if lose_at == "response":
            await expire(sessions, run_id)
        return result

    monkeypatch.setattr(adapter, "connect_read_tools", observed)
    monkeypatch.setattr(ClientSession, "call_tool", call_tool)
    with pytest.raises(OwnershipLost):
        await worker.work_mcp_once(sessions, run_id=run_id, allow_read=True)
    assert calls == int(lose_at == "response")
    state = await worker.work_mcp_once(sessions, run_id=run_id)
    assert state is not None and state.error_code == "execution_interrupted"
    assert calls == int(lose_at == "response")
