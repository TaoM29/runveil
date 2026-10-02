"""Durable search evidence cannot be forged, omitted or replayed."""

import asyncio
import json
from pathlib import Path
from typing import Literal
from uuid import UUID

import pytest
from runveil_core.agents import JsonValue
from runveil_core.models import ModelRequest
from runveil_core.runtime import Cursor, Pending, RuntimeConfig, RuntimeState
from runveil_core.sandbox_search import SEARCH_TOOL
from runveil_persistence.execution import PostgresExecutionStore
from runveil_persistence.models import ApprovalRow, ToolCallRow
from runveil_worker import sandbox_patch_worker as worker
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from test_sandbox_worker import IMAGE, DockerStub, expire
from test_sandbox_worker import docker_stub as docker_stub
from test_software_worker import workflow_output

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.mark.parametrize("cut", ["intent", "checkpoint", "forged_outcome", "forged_context"])
async def test_search_durable_boundary_and_recovery(
    database: AsyncEngine, docker_stub: DockerStub, monkeypatch: pytest.MonkeyPatch, cut: str
) -> None:
    workflow_output(docker_stub, monkeypatch)
    sessions = async_sessionmaker(database)
    run_id = await worker.submit_patch(
        sessions, IMAGE, socket=docker_stub.endpoint, workflow=True, search=True
    )

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
            if cut == "forged_context" and kind == "model":
                request = ModelRequest.model_validate_json(json.dumps(payload))
                if any(m.tool_name == SEARCH_TOOL for m in request.messages):
                    request = request.model_copy(
                        update={
                            "messages": tuple(
                                m.model_copy(
                                    update={
                                        "content": json.dumps(
                                            json.loads(m.content) | {"matches": []}
                                        )
                                    }
                                )
                                if m.tool_name == SEARCH_TOOL
                                else m
                                for m in request.messages
                            )
                        }
                    )
                    payload = request.model_dump(mode="json")
            pending = await super().request(
                cursor,
                kind=kind,
                payload=payload,
                config=config,
                model_invocation_id=model_invocation_id,
                tool_name=tool_name,
            )
            if tool_name == SEARCH_TOOL and cut == "intent":
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
            async with sessions() as session:
                call = (
                    await session.get(ToolCallRow, pending.id) if pending.kind == "tool" else None
                )
                searched = call is not None and call.tool_name == SEARCH_TOOL
            if searched and cut == "forged_outcome":
                assert result
                result = result | {"inspection_digest": "0" * 64}
            cursor = await super().complete(pending, state, result=result, error_code=error_code)
            if searched and cut == "checkpoint":
                raise asyncio.CancelledError
            return cursor

    with monkeypatch.context() as patched:
        patched.setattr(worker, "PostgresExecutionStore", Cut)
        with pytest.raises(
            asyncio.CancelledError if cut in ("intent", "checkpoint") else ValueError
        ):
            await worker.work_patch_once(
                sessions,
                run_id=run_id,
                image=IMAGE,
                socket=docker_stub.endpoint,
                allow_execute=True,
                workflow=True,
                search=True,
            )
    async with sessions() as session:
        assert await session.scalar(select(ApprovalRow.id)) is None
    starts = docker_stub.operations.count("start")
    await expire(sessions, run_id)
    clean = cut == "checkpoint"
    state = await worker.work_patch_once(
        sessions,
        run_id=run_id,
        image=IMAGE if clean else None,
        socket=docker_stub.endpoint if clean else Path("/missing"),
        allow_execute=clean,
        workflow=True,
        search=True,
    )
    assert state
    assert bool(state.approval_id) == clean
    assert state.error_code == (None if clean else "execution_interrupted")
    assert docker_stub.operations.count("start") == starts + int(clean)
    async with sessions.begin() as session:
        calls = list(
            await session.scalars(select(ToolCallRow).where(ToolCallRow.tool_name == SEARCH_TOOL))
        )
        assert (
            len(calls) == 1
        )  # Clean continuation reuses search; uncertain intent never repeats it.
        evidence = await worker.inspect_patch(session, run_id, workflow=True, search=True)
        assert evidence["status"] == ("WAITING_FOR_APPROVAL" if clean else "FAILED")
