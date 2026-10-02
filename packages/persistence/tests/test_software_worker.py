"""End-to-end fixture workflow and its new baseline/proposal boundary."""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Literal
from uuid import UUID

import pytest
from runveil_core.agents import JsonValue
from runveil_core.models import FinalResult, FinishAction, ModelRequest, ModelResponse, TokenUsage
from runveil_core.mutations import APPLY_TOOL
from runveil_core.runtime import Cursor, Pending, RuntimeConfig, RuntimeState
from runveil_core.sandbox import TEST_TOOL
from runveil_core.sandbox_patch import PATCH_UNKNOWN
from runveil_core.sandbox_review import INSPECT_TOOL
from runveil_core.software import SOFTWARE_PROFILE
from runveil_core.tools import ToolError
from runveil_persistence.approvals import ApprovalRepository
from runveil_persistence.execution import PostgresExecutionStore
from runveil_persistence.models import ModelInvocationRow, ToolCallRow
from runveil_persistence.repositories import RunRepository
from runveil_persistence.traces import read_trace
from runveil_persistence.worker_approvals import resolve_worker_review
from runveil_tools import sandbox as docker_module
from runveil_worker import sandbox_patch_worker as worker
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from test_sandbox_patch_worker import patch_output
from test_sandbox_worker import IMAGE, DockerStub, expire
from test_sandbox_worker import docker_stub as docker_stub

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def workflow_output(
    stub: DockerStub, monkeypatch: pytest.MonkeyPatch, *, passed: bool = False
) -> None:
    patch_output(stub, monkeypatch)
    command = docker_module._command
    inspected = stub.start_output

    async def execute(
        args: tuple[str, ...], timeout: float, data: bytes | None = None
    ) -> docker_module._CommandResult:
        if args[3] == "create":
            baseline = args[-1] == "clamp-v1"
            stub.exit_code = int(baseline and not passed)
            stub.start_output = b"controlled baseline" if baseline else inspected
        return await command(args, timeout, data)

    monkeypatch.setattr(docker_module, "_command", execute)


async def decide(
    sessions: async_sessionmaker[AsyncSession], run_id: UUID, *, reject: bool = False
) -> None:
    async with sessions.begin() as session:
        run = await RunRepository(session).get(run_id)
        approval = await ApprovalRepository(session).get(run_id)
        await resolve_worker_review(
            session,
            run_id,
            decision="REJECTED" if reject else "APPROVED",
            expected_revision=run.revision,
            expected_digest=approval.digest,
            profile=SOFTWARE_PROFILE,
        )


@pytest.mark.parametrize("early_finish", [False, True])
async def test_preproposal_failures_remain_inspectable(
    database: AsyncEngine,
    docker_stub: DockerStub,
    monkeypatch: pytest.MonkeyPatch,
    early_finish: bool,
) -> None:
    workflow_output(docker_stub, monkeypatch, passed=True)
    if early_finish:

        async def finish(self: worker.SoftwareProvider, request: ModelRequest) -> ModelResponse:
            return ModelResponse(
                model=request.model,
                content=FinishAction(
                    action="finish", result=FinalResult(summary="unsupported success", artifacts=())
                ).model_dump_json(),
                finish_reason="stop",
                latency_ms=0.0,
                usage=TokenUsage(input_tokens=10, output_tokens=5),
            )

        monkeypatch.setattr(worker.SoftwareProvider, "generate", finish)
    sessions = async_sessionmaker(database)
    run_id = await worker.submit_patch(sessions, IMAGE, socket=docker_stub.endpoint, workflow=True)
    async with sessions.begin() as session:
        queued = await worker.inspect_patch(session, run_id, workflow=True)
        assert queued["status"] == "QUEUED" and queued["tools"] == []
    state = await worker.work_patch_once(
        sessions,
        run_id=run_id,
        image=IMAGE,
        socket=docker_stub.endpoint,
        allow_execute=True,
        workflow=True,
    )
    assert state and state.error_code == (
        "invalid_response" if early_finish else "sandbox_baseline_invalid"
    )
    async with sessions.begin() as session:
        evidence = await worker.inspect_patch(session, run_id, workflow=True)
        assert evidence["status"] == "FAILED" and evidence["approval"] is None
        assert evidence["patch_applied"] is False and evidence["mutation"] is None
        assert evidence["error_code"] == state.error_code
        calls = list(
            await session.scalars(
                select(ToolCallRow).order_by(ToolCallRow.requested_event_sequence)
            )
        )
        assert [c.tool_name for c in calls] == ([] if early_finish else [INSPECT_TOOL, TEST_TOOL])
        if calls:
            assert calls[-1].status == "SUCCEEDED" and calls[-1].result
            assert calls[-1].result["status"] == "passed"
    assert await worker.work_patch_once(sessions, run_id=run_id, workflow=True) is None


@pytest.mark.parametrize("missing", [False, True])
async def test_changed_baseline_context_cannot_create_approval(
    database: AsyncEngine, docker_stub: DockerStub, monkeypatch: pytest.MonkeyPatch, missing: bool
) -> None:
    workflow_output(docker_stub, monkeypatch)
    sessions = async_sessionmaker(database)
    run_id = await worker.submit_patch(sessions, IMAGE, socket=docker_stub.endpoint, workflow=True)

    class ChangedContext(PostgresExecutionStore):
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
            if kind == "model":
                request = ModelRequest.model_validate_json(json.dumps(payload))
                if any(m.tool_name == TEST_TOOL for m in request.messages):
                    messages = tuple(
                        m.model_copy(
                            update={
                                "content": json.dumps(
                                    json.loads(m.content) | {"output": "invented evidence"}
                                )
                            }
                        )
                        if m.tool_name == TEST_TOOL
                        else m
                        for m in request.messages
                        if not (missing and m.tool_name == TEST_TOOL)
                    )
                    payload = request.model_copy(update={"messages": messages}).model_dump(
                        mode="json"
                    )
            return await super().request(
                cursor,
                kind=kind,
                payload=payload,
                config=config,
                model_invocation_id=model_invocation_id,
                tool_name=tool_name,
            )

    monkeypatch.setattr(worker, "PostgresExecutionStore", ChangedContext)
    # Core sees the genuine context; persistence independently rejects this mismatched journal.
    with pytest.raises(ValueError, match="recorded failing baseline"):
        await worker.work_patch_once(
            sessions,
            run_id=run_id,
            image=IMAGE,
            socket=docker_stub.endpoint,
            allow_execute=True,
            workflow=True,
        )
    async with sessions() as session:
        from runveil_persistence.models import ApprovalRow

        assert await session.scalar(select(ApprovalRow.id)) is None
        assert (
            await session.scalar(select(ToolCallRow.id).where(ToolCallRow.tool_name == APPLY_TOOL))
            is None
        )
    assert docker_stub.operations.count("start") == 2


@pytest.mark.parametrize("cut", ["baseline", "mutation"])
async def test_checkpoint_reuse_and_uncertain_effect_never_replay(
    database: AsyncEngine, docker_stub: DockerStub, monkeypatch: pytest.MonkeyPatch, cut: str
) -> None:
    workflow_output(docker_stub, monkeypatch)
    sessions = async_sessionmaker(database)
    run_id = await worker.submit_patch(sessions, IMAGE, socket=docker_stub.endpoint, workflow=True)

    class Stop(PostgresExecutionStore):
        async def complete(
            self,
            pending: Pending,
            state: RuntimeState,
            *,
            result: dict[str, JsonValue] | None = None,
            error_code: str | None = None,
        ) -> Cursor:
            if pending.kind == "tool":
                async with sessions() as session:
                    call = await session.get(ToolCallRow, pending.id)
                    assert call
                    if call.tool_name == (TEST_TOOL if cut == "baseline" else APPLY_TOOL):
                        raise asyncio.CancelledError  # Effect observed, outcome not committed.
                    if call.tool_name == INSPECT_TOOL:
                        await super().complete(pending, state, result=result, error_code=error_code)
                        raise asyncio.CancelledError  # Clean inspection checkpoint.
            return await super().complete(pending, state, result=result, error_code=error_code)

    with monkeypatch.context() as patched:
        patched.setattr(worker, "PostgresExecutionStore", Stop)
        with pytest.raises(asyncio.CancelledError):
            await worker.work_patch_once(
                sessions,
                run_id=run_id,
                image=IMAGE,
                socket=docker_stub.endpoint,
                allow_execute=True,
                workflow=True,
            )
        assert docker_stub.operations.count("start") == 1
        await expire(sessions, run_id)
        if cut == "baseline":
            with pytest.raises(asyncio.CancelledError):
                await worker.work_patch_once(
                    sessions,
                    run_id=run_id,
                    image=IMAGE,
                    socket=docker_stub.endpoint,
                    allow_execute=True,
                    workflow=True,
                )
        else:
            state = await worker.work_patch_once(
                sessions,
                run_id=run_id,
                image=IMAGE,
                socket=docker_stub.endpoint,
                allow_execute=True,
                workflow=True,
            )
            assert state and state.approval_id
            await decide(sessions, run_id)
            with pytest.raises(ToolError):
                await worker.work_patch_once(
                    sessions,
                    run_id=run_id,
                    image=IMAGE,
                    socket=docker_stub.endpoint,
                    allow_execute=True,
                    workflow=True,
                )
            await expire(sessions, run_id)
            with pytest.raises(asyncio.CancelledError):
                await worker.work_patch_once(
                    sessions,
                    run_id=run_id,
                    image=IMAGE,
                    socket=docker_stub.endpoint,
                    allow_execute=True,
                    allow_write=True,
                    workflow=True,
                )
    before = list(docker_stub.operations)
    assert before.count("start") == (2 if cut == "baseline" else 3)
    await expire(sessions, run_id)
    state = await worker.work_patch_once(
        sessions, run_id=run_id, socket=Path("/missing"), workflow=True
    )
    assert state and state.error_code == (
        "execution_interrupted" if cut == "baseline" else PATCH_UNKNOWN
    )
    assert docker_stub.operations == before
    async with sessions.begin() as session:
        evidence = await worker.inspect_patch(session, run_id, workflow=True)
        assert evidence["status"] == "FAILED"
        assert evidence["patch_applied"] is (False if cut == "baseline" else None)


async def test_real_docker_engineering_workflow_in_fresh_processes(database: AsyncEngine) -> None:
    image = os.environ.get("RUNVEIL_SANDBOX_IMAGE")
    if not image:
        pytest.skip("Set RUNVEIL_SANDBOX_IMAGE for Docker acceptance")
    sessions = async_sessionmaker(database)

    async def cli(*args: str) -> dict[str, JsonValue]:
        child = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "runveil_worker.software_worker",
            *args,
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
            assert b"return min" not in stderr and b"controlled baseline" not in stderr
            result: dict[str, JsonValue] = json.loads(stdout)
            return result
        finally:
            if child.returncode is None:
                child.kill()
            await child.wait()

    for decision in ("approve", "reject"):
        run_id = str((await cli("submit", "--image", image))["run_id"])
        assert (await cli("inspect", "--run-id", run_id))["status"] == "QUEUED"
        assert (await cli("work", "--run-id", run_id, "--image", image, "--allow-execute"))[
            "approval_id"
        ]
        review = await cli("inspect", "--run-id", run_id)
        assert review["patch_applied"] is False and review["mutation"] is None
        approval = review["approval"]
        assert isinstance(approval, dict)
        assert "+    return min(max(value, lower), upper)" in str(review["diff"])
        # Neither extra grants nor the old patch worker can consume a waiting workflow.
        assert not (
            await cli(
                "work", "--run-id", run_id, "--image", image, "--allow-execute", "--allow-write"
            )
        )["selected"]
        assert await worker.work_patch_once(sessions, run_id=UUID(run_id)) is None
        await cli(
            decision,
            "--run-id",
            run_id,
            "--revision",
            str(review["revision"]),
            "--digest",
            str(approval["digest"]),
        )
        completed = await cli(
            "work", "--run-id", run_id, "--image", image, "--allow-execute", "--allow-write"
        )
        evidence = await cli("inspect", "--run-id", run_id)
        assert evidence["status"] == ("SUCCEEDED" if decision == "approve" else "FAILED")
        assert evidence["patch_applied"] is (decision == "approve")
        if decision == "approve":
            assert completed["summary"] == "Applied the approved sandbox patch; tests passed."
        async with sessions() as session:
            calls = list(
                await session.scalars(
                    select(ToolCallRow)
                    .where(ToolCallRow.run_id == UUID(run_id))
                    .order_by(ToolCallRow.requested_event_sequence)
                )
            )
            assert [call.tool_name for call in calls] == [
                INSPECT_TOOL,
                TEST_TOOL,
                "repository.propose_patch",
            ] + ([APPLY_TOOL] if decision == "approve" else [])
            assert calls[1].result and calls[1].result["status"] == "tests_failed"
            if decision == "approve":
                assert calls[-1].result and calls[-1].result["cleanup_confirmed"] is True
                tests = calls[-1].result["tests"]
                assert isinstance(tests, dict) and tests["status"] == "passed"
            models = list(
                await session.scalars(
                    select(ModelInvocationRow)
                    .where(ModelInvocationRow.run_id == UUID(run_id))
                    .order_by(ModelInvocationRow.requested_event_sequence)
                )
            )
            assert len(models) == 3
            assert (
                calls[1].completed_event_sequence
                and calls[1].completed_event_sequence < models[2].requested_event_sequence
            )
            trace = await read_trace(session, UUID(run_id))
            assert trace.checkpoint and trace.checkpoint.schema_version == 15
            for call in calls:
                if call.tool_name == "repository.propose_patch":
                    continue
                absent = await docker_module._command(
                    (
                        *docker_module.FixtureSandbox(image)._docker,
                        "ps",
                        "-aq",
                        "--filter",
                        "name=^/runveil-sandbox-" + call.id.hex + "$",
                    ),
                    15,
                )
                assert absent.code == 0 and not absent.output.strip()
        assert not (await cli("work", "--run-id", run_id))["selected"]
