"""Durable sandbox authorization, fencing, recovery and optional real Docker acceptance."""

import asyncio
import json
import os
import shutil
import socket
import sys
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal
from uuid import UUID

import pytest
import pytest_asyncio
from runveil_core.agents import JsonValue
from runveil_core.runtime import Cursor, Pending, RuntimeConfig, RuntimeState, execute
from runveil_core.sandbox import SANDBOX_PROFILE, TEST_TOOL
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
from runveil_tools import sandbox as docker_module
from runveil_tools.sandbox_execution import BoundSandbox
from runveil_worker.sandbox_worker import (
    POLICY,
    SandboxProvider,
    sandbox_configuration,
    submit_sandbox,
    work_sandbox_once,
)
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]
IMAGE = "sha256:" + "a" * 64


class DockerStub:
    def __init__(self, endpoint: Path) -> None:
        self.endpoint = endpoint
        self.operations: list[str] = []
        self.start_output = b"controlled failing test"
        self.exit_code = 1
        self.hook: Callable[[str], Awaitable[None]] | None = None

    async def command(self, args: tuple[str, ...], timeout: float) -> docker_module._CommandResult:
        operation = args[3]
        self.operations.append(operation)
        if self.hook:
            await self.hook(operation)
        if operation == "start":
            return docker_module._CommandResult(self.exit_code, self.start_output)
        if operation == "inspect":
            return docker_module._CommandResult(
                0,
                json.dumps(
                    {
                        "Status": "exited",
                        "ExitCode": self.exit_code,
                        "OOMKilled": False,
                        "Error": "",
                    }
                ).encode(),
            )
        return docker_module._CommandResult(0, b"")


@pytest_asyncio.fixture
async def docker_stub(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[DockerStub]:
    with (
        TemporaryDirectory(prefix="rv-sock-", dir="/tmp") as directory,
        socket.socket(socket.AF_UNIX) as listener,
    ):
        endpoint = Path(directory) / "docker.sock"
        listener.bind(str(endpoint))
        stub = DockerStub(endpoint)
        monkeypatch.setattr(shutil, "which", lambda name: "/operator/docker")
        monkeypatch.setattr(docker_module, "_command", stub.command)
        yield stub


async def expire(sessions: async_sessionmaker[AsyncSession], run_id: UUID) -> None:
    async with sessions.begin() as session:
        await session.execute(
            text(
                "UPDATE worker_jobs SET expires_at=clock_timestamp() - interval '1 second' "
                "WHERE run_id=:id"
            ),
            {"id": run_id},
        )


async def test_authorization_and_binding_drift_prevent_dispatch(
    database: AsyncEngine,
    docker_stub: DockerStub,
) -> None:
    sessions = async_sessionmaker(database)
    run_id = await submit_sandbox(sessions, IMAGE, socket=docker_stub.endpoint)
    async with sessions() as session:
        before = await HistoryRepository(session).events(run_id)
    with pytest.raises(ToolError, match="tool_permission_denied"):
        await work_sandbox_once(sessions, run_id=run_id, image=IMAGE, socket=docker_stub.endpoint)
    await expire(sessions, run_id)
    with pytest.raises(ConfigurationRejected, match="worker profile"):
        await work_sandbox_once(
            sessions,
            run_id=run_id,
            image="sha256:" + "b" * 64,
            socket=docker_stub.endpoint,
            allow_execute=True,
        )
    assert not docker_stub.operations
    async with sessions() as session:
        assert await HistoryRepository(session).events(run_id) == before
        assert await session.scalar(select(ModelInvocationRow.id)) is None
    await expire(sessions, run_id)
    state = await work_sandbox_once(
        sessions,
        run_id=run_id,
        image=IMAGE,
        socket=docker_stub.endpoint,
        allow_execute=True,
    )
    assert state is not None and state.final_result is not None
    assert state.final_result.summary == "Sandbox test status: tests_failed."
    assert state.steps_used == 3 and state.tokens.attempts == 2
    async with sessions() as session:
        call = (await session.scalars(select(ToolCallRow))).one()
        assert call.status == "SUCCEEDED" and call.result is not None
        assert call.result["status"] == "tests_failed" and call.model_invocation_id is not None
        trace = await read_trace(session, run_id)
        assert trace.checkpoint is not None and trace.checkpoint.schema_version == 12
        assert trace.checkpoint.tokens == state.tokens and trace.checkpoint.cost == state.cost
        assert trace.checkpoint.final_summary == state.final_result.summary
        assert trace.tool_calls == 1 and trace.approval is None
    assert await work_sandbox_once(sessions, run_id=run_id) is None
    assert docker_stub.operations == ["create", "start", "inspect", "rm", "ps"]


@pytest.mark.parametrize("cut", ["model_checkpoint", "tool_checkpoint", "tool_intent"])
async def test_checkpoint_recovery_and_uncertain_intent_never_replay(
    database: AsyncEngine,
    docker_stub: DockerStub,
    cut: str,
) -> None:
    sessions = async_sessionmaker(database)
    run_id = await submit_sandbox(sessions, IMAGE, socket=docker_stub.endpoint)
    binding = BoundSandbox(IMAGE, socket=docker_stub.endpoint)
    config = sandbox_configuration(binding.identity)
    claim = await claim_next(sessions, profile=SANDBOX_PROFILE, run_id=run_id)
    assert claim is not None

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
            if cut == "tool_intent" and kind == "tool":
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
            if cut == pending.kind + "_checkpoint":
                raise asyncio.CancelledError
            return cursor

    with pytest.raises(asyncio.CancelledError):
        await execute(
            run_id,
            claim.task,
            provider_name=config.provider,
            provider=SandboxProvider(),
            sandbox=binding,
            tool_policy=POLICY,
            store=Stop(sessions, claim=claim, expected_config=config),
        )
    assert await work_sandbox_once(sessions, run_id=run_id) is None  # Live lease, no dispatch.
    await expire(sessions, run_id)
    state = await work_sandbox_once(
        sessions,
        run_id=run_id,
        image=None if cut == "tool_intent" else IMAGE,
        socket=Path("/missing/socket") if cut == "tool_intent" else docker_stub.endpoint,
        allow_execute=cut != "tool_intent",
    )
    assert state is not None
    if cut == "tool_intent":
        assert state.error_code == "execution_interrupted" and not docker_stub.operations
    else:
        assert state.final_result is not None and state.steps_used == 3
        assert docker_stub.operations.count("start") == 1
    async with sessions() as session:
        calls = list(await session.scalars(select(ToolCallRow)))
        assert len(calls) == 1
        assert calls[0].error_code == ("execution_interrupted" if cut == "tool_intent" else None)
        assert await load_runtime_state(session, run_id) == state


@pytest.mark.parametrize("lose_at", ["create", "start"])
async def test_fence_prevents_start_or_rejects_late_outcome(
    database: AsyncEngine,
    docker_stub: DockerStub,
    lose_at: str,
) -> None:
    sessions = async_sessionmaker(database)
    run_id = await submit_sandbox(sessions, IMAGE, socket=docker_stub.endpoint)

    async def lose(operation: str) -> None:
        if operation == lose_at:
            async with sessions() as session:
                call = (await session.scalars(select(ToolCallRow))).one()
                assert call.status == "REQUESTED" and call.tool_name == TEST_TOOL
            await expire(sessions, run_id)

    docker_stub.hook = lose
    with pytest.raises(OwnershipLost):
        await work_sandbox_once(
            sessions,
            run_id=run_id,
            image=IMAGE,
            socket=docker_stub.endpoint,
            allow_execute=True,
        )
    assert docker_stub.operations[-2:] == ["rm", "ps"]
    assert docker_stub.operations.count("start") == int(lose_at == "start")
    before = list(docker_stub.operations)
    state = await work_sandbox_once(
        sessions, run_id=run_id
    )  # No Docker/grant for terminal recovery.
    assert state is not None and state.error_code == "execution_interrupted"
    assert docker_stub.operations == before


async def test_real_docker_worker_in_fresh_process(database: AsyncEngine) -> None:
    image = os.environ.get("RUNVEIL_SANDBOX_IMAGE")
    if not image:
        pytest.skip("Set RUNVEIL_SANDBOX_IMAGE to the reviewed built image for Docker acceptance")
    sessions = async_sessionmaker(database)
    run_id = await submit_sandbox(sessions, image)
    child = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "runveil_worker.sandbox_worker",
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
        assert json.loads(stdout)["summary"] == "Sandbox test status: tests_failed."
        async with sessions() as session:
            assert (await RunRepository(session).get(run_id)).status == "SUCCEEDED"
            call = (await session.scalars(select(ToolCallRow))).one()
            assert call.result is not None and call.result["cleanup_confirmed"] is True
            assert "AssertionError" in str(call.result["output"])
            name = "runveil-sandbox-" + call.id.hex
            spans = [json.loads(line) for line in stderr.splitlines()]
            dispatched = [span for span in spans if span["name"] == "tool.dispatch"]
            assert len(dispatched) == 1
            assert dispatched[0]["attributes"]["invocation_id"] == str(call.id)
            assert b"AssertionError" not in stderr
        result = await docker_module._command(
            (
                *docker_module.FixtureSandbox(image)._docker,
                "ps",
                "-aq",
                "--filter",
                f"name=^/{name}$",
            ),
            15,
        )
        assert result.code == 0 and not result.output.strip()
    finally:
        if child.returncode is None:
            child.kill()
        await child.wait()


async def test_model_arguments_cannot_change_execution_and_cleanup_failure_is_safe(
    database: AsyncEngine,
    docker_stub: DockerStub,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from runveil_core.models import ModelRequest, ModelResponse, TokenUsage, ToolAction

    sessions = async_sessionmaker(database)

    async def injected(self: SandboxProvider, request: ModelRequest) -> ModelResponse:
        return ModelResponse(
            model="fixture-v1",
            finish_reason="stop",
            latency_ms=0.0,
            usage=TokenUsage(input_tokens=10, output_tokens=5),
            content=ToolAction(
                action="tool_call",
                tool_name=TEST_TOOL,
                arguments={"command": "untrusted"},
                decision_summary="Attempt to change the fixed command.",
            ).model_dump_json(),
        )

    with monkeypatch.context() as patched:
        patched.setattr(SandboxProvider, "generate", injected)
        run_id = await submit_sandbox(sessions, IMAGE, socket=docker_stub.endpoint)
        state = await work_sandbox_once(
            sessions,
            run_id=run_id,
            image=IMAGE,
            socket=docker_stub.endpoint,
            allow_execute=True,
        )
        assert state is not None and state.error_code == "invalid_tool_arguments"
        assert not docker_stub.operations

    async def cleanup_failure(
        args: tuple[str, ...], timeout: float
    ) -> docker_module._CommandResult:
        if args[3] == "ps":
            return docker_module._CommandResult(1, b"sensitive daemon detail")
        return await docker_stub.command(args, timeout)

    monkeypatch.setattr(docker_module, "_command", cleanup_failure)
    run_id = await submit_sandbox(sessions, IMAGE, socket=docker_stub.endpoint)
    state = await work_sandbox_once(
        sessions,
        run_id=run_id,
        image=IMAGE,
        socket=docker_stub.endpoint,
        allow_execute=True,
    )
    assert state is not None and state.error_code == "sandbox_cleanup_unconfirmed"
    assert "sensitive" not in state.model_dump_json()
    async with sessions() as session:
        call = (
            await session.scalars(select(ToolCallRow).where(ToolCallRow.run_id == run_id))
        ).one()
        assert call.result is None and call.error_code == state.error_code
