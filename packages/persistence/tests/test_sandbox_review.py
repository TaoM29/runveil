"""Sandbox preimage/proposal provenance, review recovery and real-container acceptance."""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Literal
from uuid import UUID

import pytest
from runveil_core.agents import JsonValue
from runveil_core.approvals import PROPOSAL_TOOL
from runveil_core.errors import RevisionConflict
from runveil_core.models import ModelRequest, ModelResponse, ToolAction
from runveil_core.runtime import Cursor, Pending, RuntimeConfig, RuntimeState, execute
from runveil_core.sandbox_review import (
    INSPECT_TOOL,
    REVIEW_POLICY,
    SANDBOX_REVIEW_PROFILE,
    InspectionResult,
)
from runveil_core.tools import ToolError
from runveil_persistence.execution import ConfigurationRejected, PostgresExecutionStore
from runveil_persistence.jobs import claim_next
from runveil_persistence.models import ApprovalRow, ToolCallRow
from runveil_persistence.repositories import RunRepository
from runveil_persistence.traces import read_trace
from runveil_persistence.worker_approvals import resolve_worker_review
from runveil_tools.sandbox_execution import BoundSandbox
from runveil_worker.sandbox_review_worker import (
    SandboxReviewProvider,
    inspect_review,
    review_configuration,
    submit_review,
    work_review_once,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from test_sandbox_worker import IMAGE, DockerStub, expire
from test_sandbox_worker import docker_stub as docker_stub

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]
ROOT = Path(__file__).resolve().parents[3]


def inspection_output(stub: DockerStub) -> None:
    stub.exit_code = 0
    stub.start_output = json.dumps(
        {
            "files": [
                {"path": path, "content": (ROOT / "sandbox/fixtures/clamp-v1" / path).read_text()}
                for path in ("TASK.md", "clamp.py", "test_clamp.py")
            ]
        }
    ).encode()


@pytest.mark.parametrize("decision", ["APPROVED", "REJECTED"])
async def test_exact_review_decision_and_no_mutation(
    database: AsyncEngine, docker_stub: DockerStub, decision: Literal["APPROVED", "REJECTED"]
) -> None:
    inspection_output(docker_stub)
    sessions = async_sessionmaker(database)
    run_id = await submit_review(sessions, IMAGE, socket=docker_stub.endpoint)
    with pytest.raises(ToolError):
        await work_review_once(sessions, run_id=run_id, image=IMAGE, socket=docker_stub.endpoint)
    await expire(sessions, run_id)
    with pytest.raises(ConfigurationRejected):
        await work_review_once(
            sessions,
            run_id=run_id,
            image="sha256:" + "b" * 64,
            socket=docker_stub.endpoint,
            allow_execute=True,
        )
    assert not docker_stub.operations
    await expire(sessions, run_id)
    state = await work_review_once(
        sessions, run_id=run_id, image=IMAGE, socket=docker_stub.endpoint, allow_execute=True
    )
    assert state and state.approval_id and state.steps_used == 4
    assert await work_review_once(sessions, run_id=run_id) is None
    async with sessions.begin() as session:
        evidence = await inspect_review(session, run_id)
        run = await RunRepository(session).get(run_id)
        approval = await session.get(ApprovalRow, state.approval_id)
        assert approval and run.status == "WAITING_FOR_APPROVAL"
        digest = approval.digest
        assert evidence["patch_applied"] is False
        assert "+    return min(max(value, lower), upper)" in str(evidence["diff"])
        inspection = InspectionResult.model_validate_json(docker_stub.start_output)
        assert evidence["inspection_digest"] == inspection.digest
        trace = await read_trace(session, run_id)
        assert trace.checkpoint and trace.checkpoint.schema_version == 13
        assert trace.checkpoint.tokens == state.tokens and trace.approval
    with pytest.raises(RevisionConflict):
        async with sessions.begin() as session:
            await resolve_worker_review(
                session,
                run_id,
                decision=decision,
                expected_revision=run.revision,
                expected_digest="0" * 64,
                profile=SANDBOX_REVIEW_PROFILE,
            )
    async with sessions.begin() as session:
        await resolve_worker_review(
            session,
            run_id,
            decision=decision,
            expected_revision=run.revision,
            expected_digest=digest,
            profile=SANDBOX_REVIEW_PROFILE,
        )
    with pytest.raises(RevisionConflict):
        async with sessions.begin() as session:
            await resolve_worker_review(
                session,
                run_id,
                decision=decision,
                expected_revision=run.revision,
                expected_digest=digest,
                profile=SANDBOX_REVIEW_PROFILE,
            )
    result = await work_review_once(
        sessions, run_id=run_id, image=IMAGE, socket=docker_stub.endpoint, allow_execute=True
    )
    if decision == "APPROVED":
        assert result and result.final_result and result.steps_used == 5
        assert result.tokens.attempts == 3 and "No patch was applied" in result.final_result.summary
    else:
        assert result is None
    async with sessions() as session:
        calls = list(await session.scalars(select(ToolCallRow)))
        assert [
            call.tool_name for call in sorted(calls, key=lambda c: c.requested_event_sequence)
        ] == [INSPECT_TOOL, PROPOSAL_TOOL]
    assert docker_stub.operations == ["create", "start", "inspect", "rm", "ps"]


@pytest.mark.parametrize("cut", ["inspection_checkpoint", "inspection_intent", "proposal_intent"])
async def test_review_recovery_uses_recorded_preimage_without_replay(
    database: AsyncEngine, docker_stub: DockerStub, cut: str
) -> None:
    inspection_output(docker_stub)
    sessions = async_sessionmaker(database)
    run_id = await submit_review(sessions, IMAGE, socket=docker_stub.endpoint)
    binding = BoundSandbox(IMAGE, socket=docker_stub.endpoint)
    config = review_configuration(binding.identity)
    claim = await claim_next(sessions, profile=SANDBOX_REVIEW_PROFILE, run_id=run_id)
    assert claim

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
            if (
                cut == "inspection_intent"
                and tool_name == INSPECT_TOOL
                or cut == "proposal_intent"
                and tool_name == PROPOSAL_TOOL
            ):
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
            if cut == "inspection_checkpoint" and pending.kind == "tool":
                raise asyncio.CancelledError
            return cursor

    with pytest.raises(asyncio.CancelledError):
        await execute(
            run_id,
            claim.task,
            provider_name=config.provider,
            provider=SandboxReviewProvider(),
            inspection=binding,
            tool_policy=REVIEW_POLICY,
            store=Stop(sessions, claim=claim, expected_config=config),
        )
    await expire(sessions, run_id)
    clean = cut == "inspection_checkpoint"
    state = await work_review_once(
        sessions,
        run_id=run_id,
        image=IMAGE if clean else None,
        socket=docker_stub.endpoint if clean else Path("/missing/socket"),
        allow_execute=clean,
    )
    assert state
    assert bool(state.approval_id) == clean
    assert state.error_code == (None if clean else "execution_interrupted")
    assert docker_stub.operations.count("start") == (0 if cut == "inspection_intent" else 1)


@pytest.mark.parametrize(
    "attack", ["arguments", "path", "preimage", "incomplete_output", "storage_preimage"]
)
async def test_invalid_inspection_or_proposal_never_creates_approval(
    database: AsyncEngine, docker_stub: DockerStub, monkeypatch: pytest.MonkeyPatch, attack: str
) -> None:
    inspection_output(docker_stub)
    generate = SandboxReviewProvider.generate

    async def altered(self: SandboxReviewProvider, request: ModelRequest) -> ModelResponse:
        response = await generate(self, request)
        action = ToolAction.model_validate_json(response.content)
        if action.tool_name == INSPECT_TOOL and attack == "arguments":
            action = action.model_copy(update={"arguments": {"path": "../outside"}})
        elif action.tool_name == PROPOSAL_TOOL:
            arguments = dict(action.arguments)
            if attack == "path":
                arguments["path"] = "test_clamp.py"
            elif attack in ("preimage", "storage_preimage"):
                arguments["before"] = "invented preimage"
            action = action.model_copy(update={"arguments": arguments})
        return response.model_copy(update={"content": action.model_dump_json()})

    monkeypatch.setattr(SandboxReviewProvider, "generate", altered)
    if attack == "incomplete_output":
        docker_stub.start_output = b'{"files": []}'
    sessions = async_sessionmaker(database)
    run_id = await submit_review(sessions, IMAGE, socket=docker_stub.endpoint)
    if attack == "storage_preimage":
        from runveil_core import runtime

        monkeypatch.setattr(runtime, "validate_proposal", lambda proposal, inspection: None)
        with pytest.raises(ToolError, match="tool_resource_invalid"):
            await work_review_once(
                sessions,
                run_id=run_id,
                image=IMAGE,
                socket=docker_stub.endpoint,
                allow_execute=True,
            )
        async with sessions() as session:
            assert await session.scalar(select(ApprovalRow.id)) is None
            call = (
                await session.scalars(
                    select(ToolCallRow).where(ToolCallRow.tool_name == PROPOSAL_TOOL)
                )
            ).one()
            assert call.status == "REQUESTED"  # Atomic pause/outcome rolled back.
        return
    state = await work_review_once(
        sessions, run_id=run_id, image=IMAGE, socket=docker_stub.endpoint, allow_execute=True
    )
    assert state and state.error_code and state.approval_id is None
    async with sessions() as session:
        assert await session.scalar(select(ApprovalRow.id)) is None
    assert docker_stub.operations.count("create") == int(attack != "arguments")


async def test_real_docker_review_in_fresh_process(database: AsyncEngine) -> None:
    image = os.environ.get("RUNVEIL_SANDBOX_IMAGE")
    if not image:
        pytest.skip("Set RUNVEIL_SANDBOX_IMAGE for real Docker acceptance")
    sessions = async_sessionmaker(database)
    run_id = await submit_review(sessions, image)

    async def worker() -> bytes:
        child = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "runveil_worker.sandbox_review_worker",
            "work",
            "--run-id",
            str(run_id),
            "--image",
            image,
            "--allow-execute",
            env=os.environ
            | {
                "DATABASE_URL": database.url.render_as_string(hide_password=False),
                "RUNVEIL_TELEMETRY": "json",
            },
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(child.communicate(), 60)
            assert child.returncode == 0, stdout.decode()
            assert b"return min" not in stderr
            return stdout
        finally:
            if child.returncode is None:
                child.kill()
            await child.wait()

    assert json.loads(await worker())["approval_id"]
    async with sessions.begin() as session:
        evidence = await inspect_review(session, run_id)
        approval = (await session.scalars(select(ApprovalRow))).one()
        run = await RunRepository(session).get(run_id)
        assert evidence["patch_applied"] is False
        assert "return min(max(value, lower), upper)" in str(evidence["diff"])
        await resolve_worker_review(
            session,
            run_id,
            decision="APPROVED",
            expected_revision=run.revision,
            expected_digest=approval.digest,
            profile=SANDBOX_REVIEW_PROFILE,
        )
    assert "No patch was applied" in json.loads(await worker())["summary"]
    async with sessions() as session:
        calls = list(await session.scalars(select(ToolCallRow)))
        assert len(calls) == 2 and all(call.status == "SUCCEEDED" for call in calls)
        assert (await RunRepository(session).get(run_id)).status == "SUCCEEDED"


async def test_expired_review_cannot_dispatch_after_approval(
    database: AsyncEngine, docker_stub: DockerStub, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import datetime, timedelta

    from runveil_persistence import execution, jobs
    from runveil_persistence.models import JobRow

    inspection_output(docker_stub)
    sessions = async_sessionmaker(database)
    run_id = await submit_review(sessions, IMAGE, socket=docker_stub.endpoint)
    state = await work_review_once(
        sessions, run_id=run_id, image=IMAGE, socket=docker_stub.endpoint, allow_execute=True
    )
    assert state and state.approval_id
    async with sessions.begin() as session:
        approval = await session.get(ApprovalRow, state.approval_id)
        run = await RunRepository(session).get(run_id)
        assert approval
        await resolve_worker_review(
            session,
            run_id,
            decision="APPROVED",
            expected_revision=run.revision,
            expected_digest=approval.digest,
            profile=SANDBOX_REVIEW_PROFILE,
        )
        job = await session.get(JobRow, run_id)
        assert job and job.deadline_at
        after_deadline = job.deadline_at + timedelta(seconds=1)

    async def now(session: AsyncSession) -> datetime:
        return after_deadline

    monkeypatch.setattr(jobs, "database_now", now)
    monkeypatch.setattr(execution, "database_now", now)
    result = await work_review_once(
        sessions, run_id=run_id, image=IMAGE, socket=docker_stub.endpoint, allow_execute=True
    )
    assert result and result.error_code == "elapsed_time_exceeded"
    assert result.tokens == state.tokens and result.steps_used == state.steps_used
    assert docker_stub.operations.count("start") == 1
