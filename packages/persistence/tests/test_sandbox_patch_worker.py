"""Approved sandbox mutations: grants, exact provenance, fenced outcomes and no replay."""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Literal
from uuid import UUID

import pytest
from runveil_core.agents import JsonValue
from runveil_core.mutations import APPLY_TOOL
from runveil_core.runtime import Cursor, Pending, RuntimeConfig, RuntimeState
from runveil_core.sandbox import TestsResult as SandboxTestsResult
from runveil_core.sandbox_patch import (
    PATCH_UNKNOWN,
    SANDBOX_PATCH_PROFILE,
    SandboxPatchInput,
    SandboxPatchObservation,
)
from runveil_core.tools import ToolError
from runveil_persistence.approvals import ApprovalRepository
from runveil_persistence.execution import ConfigurationRejected, PostgresExecutionStore
from runveil_persistence.jobs import OwnershipLost
from runveil_persistence.models import ToolCallRow
from runveil_persistence.repositories import RunRepository
from runveil_persistence.traces import read_trace
from runveil_persistence.worker_approvals import resolve_worker_review
from runveil_tools import sandbox as docker_module
from runveil_tools.sandbox_execution import BoundSandbox
from runveil_worker import sandbox_patch_worker
from runveil_worker.sandbox_patch_worker import inspect_patch, submit_patch, work_patch_once
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from test_sandbox_review import inspection_output
from test_sandbox_worker import IMAGE, DockerStub, expire
from test_sandbox_worker import docker_stub as docker_stub

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def patch_output(
    stub: DockerStub, monkeypatch: pytest.MonkeyPatch, *, failed: bool = False
) -> None:
    inspection_output(stub)

    async def command(
        args: tuple[str, ...], timeout: float, data: bytes | None = None
    ) -> docker_module._CommandResult:
        result = await stub.command(args, timeout)
        if data is not None:
            assert args[3:6] == ("start", "--attach", "--interactive")
            payload = SandboxPatchInput.model_validate_json(data)
            observed = SandboxPatchObservation(
                proposal_digest=payload.proposal.digest,
                before_digest=payload.inspection.digest,
                after_digest=payload.postimage().digest,
                tests=SandboxTestsResult(
                    status="tests_failed" if failed else "passed",
                    exit_code=1 if failed else 0,
                    output="controlled validation",
                    output_truncated=False,
                ),
            )
            return docker_module._CommandResult(0, observed.model_dump_json().encode())
        return result

    monkeypatch.setattr(docker_module, "_command", command)


async def paused(sessions: async_sessionmaker[AsyncSession], stub: DockerStub) -> UUID:
    run_id = await submit_patch(sessions, IMAGE, socket=stub.endpoint)
    state = await work_patch_once(
        sessions, run_id=run_id, image=IMAGE, socket=stub.endpoint, allow_execute=True
    )
    assert state and state.approval_id and state.steps_used == 4
    return run_id


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
            profile=SANDBOX_PATCH_PROFILE,
        )


@pytest.mark.parametrize("failed", [False, True])
async def test_write_grant_identity_and_durable_test_outcome(
    database: AsyncEngine, docker_stub: DockerStub, monkeypatch: pytest.MonkeyPatch, failed: bool
) -> None:
    patch_output(docker_stub, monkeypatch, failed=failed)
    sessions = async_sessionmaker(database)
    run_id = await paused(sessions, docker_stub)
    assert (
        await work_patch_once(
            sessions,
            run_id=run_id,
            image=IMAGE,
            socket=docker_stub.endpoint,
            allow_execute=True,
            allow_write=True,
        )
        is None
    )
    async with sessions.begin() as session:
        evidence = await inspect_patch(session, run_id)
        assert evidence["patch_applied"] is False and evidence["mutation"] is None
    await decide(sessions, run_id)
    with pytest.raises(ToolError):
        await work_patch_once(
            sessions, run_id=run_id, image=IMAGE, socket=docker_stub.endpoint, allow_execute=True
        )
    await expire(sessions, run_id)
    with pytest.raises(ConfigurationRejected):
        await work_patch_once(
            sessions,
            run_id=run_id,
            image="sha256:" + "b" * 64,
            socket=docker_stub.endpoint,
            allow_execute=True,
            allow_write=True,
        )
    assert docker_stub.operations.count("start") == 1
    async with sessions() as session:
        assert (
            await session.scalar(select(ToolCallRow.id).where(ToolCallRow.tool_name == APPLY_TOOL))
            is None
        )
    await expire(sessions, run_id)
    result = await work_patch_once(
        sessions,
        run_id=run_id,
        image=IMAGE,
        socket=docker_stub.endpoint,
        allow_execute=True,
        allow_write=True,
    )
    assert result and result.steps_used == 5 and result.tokens.attempts == 2
    assert result.error_code == ("sandbox_validation_failed" if failed else None)
    async with sessions.begin() as session:
        evidence = await inspect_patch(session, run_id)
        assert evidence["patch_applied"] is True
        call = (
            await session.scalars(select(ToolCallRow).where(ToolCallRow.tool_name == APPLY_TOOL))
        ).one()
        assert call.status == "SUCCEEDED" and call.model_invocation_id is None and call.result
        assert "+    return min(max(value, lower), upper)" in str(call.result["approved_diff"])
        assert call.result["applied"] is True
        assert (await RunRepository(session).get(run_id)).status == (
            "FAILED" if failed else "SUCCEEDED"
        )
        trace = await read_trace(session, run_id)
        assert trace.checkpoint and trace.checkpoint.schema_version == 14
        assert trace.tool_calls == 3 and trace.checkpoint.tokens == result.tokens
    assert await work_patch_once(sessions, run_id=run_id) is None
    assert docker_stub.operations.count("start") == 2


async def test_rejection_and_review_only_approval_never_authorize_mutation(
    database: AsyncEngine, docker_stub: DockerStub, monkeypatch: pytest.MonkeyPatch
) -> None:
    from runveil_core.sandbox_review import SANDBOX_REVIEW_PROFILE
    from runveil_persistence.sandbox_mutations import authorized_sandbox_patch
    from runveil_worker.sandbox_review_worker import submit_review, work_review_once

    patch_output(docker_stub, monkeypatch)
    sessions = async_sessionmaker(database)
    run_id = await paused(sessions, docker_stub)
    await decide(sessions, run_id, reject=True)
    assert (
        await work_patch_once(
            sessions,
            run_id=run_id,
            image=IMAGE,
            socket=docker_stub.endpoint,
            allow_execute=True,
            allow_write=True,
        )
        is None
    )
    review = await submit_review(sessions, IMAGE, socket=docker_stub.endpoint)
    await work_review_once(
        sessions, run_id=review, image=IMAGE, socket=docker_stub.endpoint, allow_execute=True
    )
    async with sessions.begin() as session:
        run = await RunRepository(session).get(review)
        approval = await ApprovalRepository(session).get(review)
        await resolve_worker_review(
            session,
            review,
            decision="APPROVED",
            expected_revision=run.revision,
            expected_digest=approval.digest,
            profile=SANDBOX_REVIEW_PROFILE,
        )
    assert await work_patch_once(sessions, run_id=review) is None
    with pytest.raises(ValueError, match="dedicated profile"):
        async with sessions.begin() as session:
            await authorized_sandbox_patch(session, review)
    async with sessions() as session:
        assert (
            await session.scalar(select(ToolCallRow.id).where(ToolCallRow.tool_name == APPLY_TOOL))
            is None
        )
    assert docker_stub.operations.count("start") == 2  # Inspection only.


@pytest.mark.parametrize("cut", ["intent", "effect", "outcome"])
async def test_mutation_uncertainty_and_terminal_duplicates_never_replay(
    database: AsyncEngine, docker_stub: DockerStub, monkeypatch: pytest.MonkeyPatch, cut: str
) -> None:
    patch_output(docker_stub, monkeypatch)
    sessions = async_sessionmaker(database)
    run_id = await paused(sessions, docker_stub)
    await decide(sessions, run_id)

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
            if cut == "intent" and tool_name == APPLY_TOOL:
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
            if cut == "effect":
                raise asyncio.CancelledError
            cursor = await super().complete(pending, state, result=result, error_code=error_code)
            if cut == "outcome":
                raise asyncio.CancelledError
            return cursor

    with monkeypatch.context() as patched:
        patched.setattr(sandbox_patch_worker, "PostgresExecutionStore", Stop)
        with pytest.raises(asyncio.CancelledError):
            await work_patch_once(
                sessions,
                run_id=run_id,
                image=IMAGE,
                socket=docker_stub.endpoint,
                allow_execute=True,
                allow_write=True,
            )
    before = list(docker_stub.operations)
    await expire(sessions, run_id)
    recovered = await work_patch_once(sessions, run_id=run_id, socket=Path("/missing/socket"))
    if cut == "outcome":
        assert recovered is None
    else:
        assert recovered and recovered.error_code == PATCH_UNKNOWN and recovered.steps_used == 5
    assert docker_stub.operations == before
    async with sessions() as session:
        call = (
            await session.scalars(select(ToolCallRow).where(ToolCallRow.tool_name == APPLY_TOOL))
        ).one()
        assert call.error_code == (None if cut == "outcome" else PATCH_UNKNOWN)


@pytest.mark.parametrize("lose_at", ["create", "start"])
async def test_mutation_fences_stop_start_or_reject_late_outcome(
    database: AsyncEngine, docker_stub: DockerStub, monkeypatch: pytest.MonkeyPatch, lose_at: str
) -> None:
    patch_output(docker_stub, monkeypatch)
    sessions = async_sessionmaker(database)
    run_id = await paused(sessions, docker_stub)
    await decide(sessions, run_id)

    async def lose(operation: str) -> None:
        if operation == lose_at:
            async with sessions() as session:
                call = (
                    await session.scalars(
                        select(ToolCallRow).where(ToolCallRow.tool_name == APPLY_TOOL)
                    )
                ).one()
                assert call.status == "REQUESTED"
            await expire(sessions, run_id)

    docker_stub.hook = lose
    with pytest.raises(OwnershipLost):
        await work_patch_once(
            sessions,
            run_id=run_id,
            image=IMAGE,
            socket=docker_stub.endpoint,
            allow_execute=True,
            allow_write=True,
        )
    assert docker_stub.operations[-2:] == ["rm", "ps"]
    assert docker_stub.operations.count("start") == 1 + int(lose_at == "start")
    recovered = await work_patch_once(sessions, run_id=run_id)
    assert recovered and recovered.error_code == PATCH_UNKNOWN


async def test_real_docker_approved_patch_in_fresh_process(database: AsyncEngine) -> None:
    image = os.environ.get("RUNVEIL_SANDBOX_IMAGE")
    if not image:
        pytest.skip("Set RUNVEIL_SANDBOX_IMAGE for Docker acceptance")
    sessions = async_sessionmaker(database)
    run_id = await submit_patch(sessions, image)

    async def worker(*extra: str) -> dict[str, JsonValue]:
        child = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "runveil_worker.sandbox_patch_worker",
            "work",
            "--run-id",
            str(run_id),
            "--image",
            image,
            "--allow-execute",
            *extra,
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
            data: dict[str, JsonValue] = json.loads(stdout)
            return data
        finally:
            if child.returncode is None:
                child.kill()
            await child.wait()

    assert (await worker())["approval_id"]
    await decide(sessions, run_id)
    assert (await worker("--allow-write"))[
        "summary"
    ] == "Applied the approved sandbox patch; tests passed."
    async with sessions.begin() as session:
        evidence = await inspect_patch(session, run_id)
        assert evidence["patch_applied"] is True
        call = (
            await session.scalars(select(ToolCallRow).where(ToolCallRow.tool_name == APPLY_TOOL))
        ).one()
        assert call.result and call.result["cleanup_confirmed"] is True
        assert (await RunRepository(session).get(run_id)).status == "SUCCEEDED"
        name = "runveil-sandbox-" + call.id.hex
    result = await docker_module._command(
        (*docker_module.FixtureSandbox(image)._docker, "ps", "-aq", "--filter", f"name=^/{name}$"),
        15,
    )
    assert result.code == 0 and not result.output.strip()
    assert not (await worker("--allow-write"))["selected"]


async def test_real_docker_preimage_and_postchange_validation_boundaries() -> None:
    from uuid import uuid4

    from runveil_core.approvals import PatchProposal
    from runveil_core.sandbox_review import InspectionResult

    image = os.environ.get("RUNVEIL_SANDBOX_IMAGE")
    if not image:
        pytest.skip("Set RUNVEIL_SANDBOX_IMAGE for Docker acceptance")
    binding = BoundSandbox(image)

    async def admit() -> None:
        pass  # Direct operator adapter boundary test; durable authorization tested above.

    inspected = await binding.inspect(uuid4(), admit)
    before = inspected.files[1].content
    repaired = before.replace("return min(value, upper)", "return min(max(value, lower), upper)")
    cases = (
        ("preimage", repaired, "tool_resource_invalid"),
        ("workspace", repaired, "tool_resource_invalid"),
        ("failed", before.replace("return min(value, upper)", "return upper"), "tests_failed"),
        ("timeout", "import time\ntime.sleep(60)\n" + repaired, "timeout"),
        ("output", "print('x' * 10000)\n" + repaired, "output_limit"),
        ("drift", "open('test_clamp.py', 'w').write('# changed\\n')\n" + repaired, PATCH_UNKNOWN),
        ("extra", "open('extra', 'w').write('unexpected')\n" + repaired, PATCH_UNKNOWN),
    )
    for case, after, expected in cases:
        snapshot = inspected
        if case == "preimage":
            snapshot = InspectionResult(
                files=(
                    inspected.files[0],
                    inspected.files[1].model_copy(update={"content": before + "# drift\n"}),
                    inspected.files[2],
                )
            )
        if case == "workspace":
            snapshot = InspectionResult(
                files=(
                    inspected.files[0].model_copy(update={"content": "changed task\n"}),
                    inspected.files[1],
                    inspected.files[2],
                )
            )
        payload = SandboxPatchInput(
            approval_id=uuid4(),
            inspection=snapshot,
            proposal=PatchProposal(path="clamp.py", before=snapshot.files[1].content, after=after),
        )
        invocation_id = uuid4()
        if expected.startswith(("tool_", "sandbox_")):
            with pytest.raises(ToolError, match=expected):
                await binding.apply(invocation_id, payload, admit)
        else:
            result = await binding.apply(invocation_id, payload, admit)
            assert result.applied and result.tests.status == expected
            assert result.after_digest == payload.postimage().digest
        absent = await docker_module._command(
            (
                *docker_module.FixtureSandbox(image)._docker,
                "ps",
                "-aq",
                "--filter",
                "name=^/runveil-sandbox-" + invocation_id.hex + "$",
            ),
            15,
        )
        assert absent.code == 0 and not absent.output.strip()


async def test_durable_boundary_refuses_changed_intent_and_forged_postimage(
    database: AsyncEngine, docker_stub: DockerStub, monkeypatch: pytest.MonkeyPatch
) -> None:
    from collections.abc import Awaitable, Callable

    from runveil_core.sandbox_patch import SandboxPatchResult
    from runveil_persistence.jobs import claim_next
    from runveil_worker.sandbox_patch_worker import patch_configuration

    patch_output(docker_stub, monkeypatch)
    sessions = async_sessionmaker(database)
    run_id = await paused(sessions, docker_stub)
    await decide(sessions, run_id)
    binding = BoundSandbox(IMAGE, socket=docker_stub.endpoint)
    config = patch_configuration(binding.identity)
    claim = await claim_next(sessions, profile=SANDBOX_PATCH_PROFILE, run_id=run_id)
    assert claim
    store = PostgresExecutionStore(sessions, claim=claim, expected_config=config)
    started = await store.start(run_id, claim.task, config.provider)
    payload = await store.approved_sandbox_patch(started.cursor)
    changed = payload.model_copy(
        update={
            "proposal": payload.proposal.model_copy(update={"after": "unapproved replacement\n"})
        }
    )
    with pytest.raises(ValueError, match="exact approved proposal"):
        await store.request(
            started.cursor,
            kind="tool",
            tool_name=APPLY_TOOL,
            payload=changed.model_dump(mode="json"),
            config=config,
        )
    assert docker_stub.operations.count("start") == 1
    await expire(sessions, run_id)
    apply = BoundSandbox.apply

    async def forged(
        self: BoundSandbox,
        invocation_id: UUID,
        payload: SandboxPatchInput,
        admit: Callable[[], Awaitable[None]],
    ) -> SandboxPatchResult:
        observed = await apply(self, invocation_id, payload, admit)
        return observed.model_copy(update={"after_digest": "0" * 64})

    monkeypatch.setattr(BoundSandbox, "apply", forged)
    with pytest.raises(ValueError, match="outcome differs"):
        await work_patch_once(
            sessions,
            run_id=run_id,
            image=IMAGE,
            socket=docker_stub.endpoint,
            allow_execute=True,
            allow_write=True,
        )
    await expire(sessions, run_id)
    state = await work_patch_once(sessions, run_id=run_id)
    assert state and state.error_code == PATCH_UNKNOWN
    assert docker_stub.operations.count("start") == 2


async def test_expiry_during_mutation_retains_unknown_outcome(
    database: AsyncEngine, docker_stub: DockerStub, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import datetime, timedelta

    from runveil_persistence import execution
    from runveil_persistence.models import JobRow

    patch_output(docker_stub, monkeypatch)
    sessions = async_sessionmaker(database)
    run_id = await paused(sessions, docker_stub)
    await decide(sessions, run_id)
    async with sessions() as session:
        job = await session.get(JobRow, run_id)
        assert job and job.deadline_at
        late = job.deadline_at + timedelta(seconds=1)

    async def now(session: AsyncSession) -> datetime:
        return late

    async def lapse(operation: str) -> None:
        if operation == "start":
            monkeypatch.setattr(execution, "database_now", now)

    docker_stub.hook = lapse
    state = await work_patch_once(
        sessions,
        run_id=run_id,
        image=IMAGE,
        socket=docker_stub.endpoint,
        allow_execute=True,
        allow_write=True,
    )
    assert state and state.error_code == PATCH_UNKNOWN
    async with sessions() as session:
        call = (
            await session.scalars(select(ToolCallRow).where(ToolCallRow.tool_name == APPLY_TOOL))
        ).one()
        assert call.status == "FAILED" and call.error_code == PATCH_UNKNOWN and call.result is None
    assert await work_patch_once(sessions, run_id=run_id) is None
