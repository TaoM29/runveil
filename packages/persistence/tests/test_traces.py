"""Trace evidence agrees with durable history and never changes execution authority."""

import secrets
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from runveil_api.approvals import token_digest
from runveil_api.main import create_app
from runveil_core.runs import RunStatus
from runveil_persistence.history import HistoryRepository
from runveil_persistence.models import JobRow
from runveil_persistence.repositories import RunRepository
from runveil_persistence.traces import read_trace
from runveil_worker.patch_worker import submit_patch, work_patch_once
from runveil_worker.worker import COST_PROFILE, submit, work_once
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from test_retries import Clock
from test_retries import clock as clock

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def client(database: AsyncEngine) -> httpx.AsyncClient:
    app = create_app()
    token = secrets.token_urlsafe(32)
    app.state.database = database
    app.state.trace_token_digest = token_digest(token)
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": "Bearer " + token},
    )


async def test_trace_pagination_retries_accounting_and_payload_exclusion(
    database: AsyncEngine,
    clock: Clock,
) -> None:
    sessions = async_sessionmaker(database)
    run_id = await submit(sessions, profile=COST_PROFILE)
    # This profile has a deadline tied to the real persisted first-start timestamp.
    clock.at = datetime.now(UTC)
    async with client(database) as http:
        path = f"/runs/{run_id}/trace"
        queued = (await http.get(path)).json()
        assert queued["checkpoint"] is None and queued["elapsed_ms"] is None
        for delay in (1, 2):
            await work_once(sessions, run_id=run_id, profile=COST_PROFILE)
            clock.advance(delay)
        outcome = await work_once(sessions, run_id=run_id, profile=COST_PROFILE)
        assert outcome is not None and outcome[1].final_result is not None
        assert (
            await http.get(path, params={"expected_sequence": queued["event_sequence"]})
        ).status_code == 409
        response = await http.get(path, params={"limit": 3})
        assert response.status_code == 200, response.text
        view = response.json()
        assert view["status"] == "SUCCEEDED" and view["history_complete"]
        assert view["model_calls"] == 4 and view["tool_calls"] == 1
        assert view["checkpoint"]["tokens"] == outcome[1].tokens.model_dump(mode="json")
        assert outcome[1].cost is not None
        assert view["checkpoint"]["cost"] == outcome[1].cost.model_dump(mode="json")
        assert view["checkpoint"]["retries_scheduled"] == 2
        assert view["checkpoint"]["final_summary"] == outcome[1].final_result.summary
        events = view["events"]
        while view["next_after_sequence"] is not None:
            response = await http.get(
                path,
                params={
                    "limit": 3,
                    "after_sequence": view["next_after_sequence"],
                    "expected_sequence": view["event_sequence"],
                },
            )
            assert response.status_code == 200, response.text
            view = response.json()
            assert "Identify the public fixture." not in response.text
            events.extend(view["events"])
        async with sessions.begin() as session:
            history = await HistoryRepository(session).events(run_id)
        assert [(event["sequence"], event["kind"]) for event in events] == [
            (event.sequence, event.kind) for event in history
        ]
        assert events[-1]["to_status"] == "SUCCEEDED"
        requests = [event for event in events if event["kind"] == "model.requested"]
        assert requests[1]["retry_of"] == requests[0]["invocation"]["id"]
        assert requests[2]["retry_of"] == requests[1]["invocation"]["id"]
        assert requests[0]["invocation"]["error_code"] == "provider_rate_limited"
        assert all(event["invocation"]["duration_ms"] >= 0 for event in requests)
        assert all("payload" not in event for event in events)


async def test_trace_snapshot_does_not_lock_or_mix_concurrent_commits(
    database: AsyncEngine,
) -> None:
    sessions = async_sessionmaker(database)
    run_id = await submit(sessions)
    async with sessions.begin() as reader:
        await reader.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        before = await read_trace(reader, run_id)
        async with sessions.begin() as writer:
            await writer.execute(text("SET LOCAL lock_timeout = '500ms'"))
            await RunRepository(writer).transition(run_id, RunStatus.RUNNING, expected_revision=0)
        after = await read_trace(reader, run_id)
        assert after.event_sequence == before.event_sequence and after.status == before.status
    async with sessions.begin() as reader:
        latest = await read_trace(reader, run_id)
        assert latest.event_sequence > before.event_sequence and latest.status == RunStatus.RUNNING


async def test_approval_trace_is_read_only_and_hides_proposal(
    database: AsyncEngine, tmp_path: Path
) -> None:
    sessions = async_sessionmaker(database)
    file = tmp_path / "a.txt"
    file.write_text("private-proposal-sentinel")
    run_id = await submit_patch(sessions, tmp_path, "a.txt")
    await work_patch_once(sessions, tmp_path, "a.txt", run_id=run_id)
    async with sessions.begin() as session:
        before = await HistoryRepository(session).events(run_id)
    async with client(database) as http:
        response = await http.get(f"/runs/{run_id}/trace")
        assert response.status_code == 200, response.text
        view = response.json()
        assert view["status"] == "WAITING_FOR_APPROVAL"
        assert view["approval"]["status"] == "PENDING"
        assert (
            "private-proposal-sentinel" not in response.text and str(tmp_path) not in response.text
        )
    async with sessions.begin() as session:
        assert await HistoryRepository(session).events(run_id) == before
        job = await session.get(JobRow, run_id)
        assert job is not None and job.token is None
    assert file.read_text() == "private-proposal-sentinel"


async def test_unresolved_intent_and_legacy_accounting_are_not_zero(database: AsyncEngine) -> None:
    from runveil_persistence.invocations import InvocationRepository

    sessions = async_sessionmaker(database)
    run_id = await submit(sessions)
    async with sessions.begin() as session:
        run = await RunRepository(session).transition(
            run_id, RunStatus.RUNNING, expected_revision=0
        )
        events = await HistoryRepository(session).events(run_id)
        pending = await InvocationRepository(session).request_model(
            run_id,
            invocation_id=uuid4(),
            provider="fixture",
            model="fixture",
            request={"private": "sentinel"},
            expected_revision=run.revision,
            expected_sequence=events[-1].sequence,
        )
    async with sessions.begin() as session:
        view = await read_trace(session, run_id)
        invocation = view.events[-1].invocation
        assert invocation is not None and invocation.status == "REQUESTED"
        assert invocation.duration_ms is None and invocation.completed_at is None
        assert view.model_calls == 1 and view.checkpoint is None
        await InvocationRepository(session).complete_model(
            run_id,
            pending.id,
            expected_revision=run.revision,
            expected_sequence=view.event_sequence,
            result={"private": "sentinel"},
            state={
                "schema_version": 1,
                "final_result": {"summary": "x" * 4097},
                "messages": [{"content": "sentinel"}],
                "tokens": {"input_tokens": 0},
            },
        )
    async with client(database) as http:
        response = await http.get(f"/runs/{run_id}/trace")
        assert response.status_code == 200, response.text
        checkpoint = response.json()["checkpoint"]
        assert checkpoint["tokens"] is None and checkpoint["cost"] is None
        assert checkpoint["final_summary"] == "x" * 4096
        assert checkpoint["final_summary_truncated"]
        assert "sentinel" not in response.text
