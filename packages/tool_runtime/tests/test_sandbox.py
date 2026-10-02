import asyncio
import shutil
from pathlib import Path

import pytest
from runveil_tools import sandbox

IMAGE = "sha256:" + "a" * 64


@pytest.fixture
def runner(monkeypatch: pytest.MonkeyPatch) -> sandbox.FixtureSandbox:
    monkeypatch.setattr(Path, "is_socket", lambda self: True)
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/docker")
    return sandbox.FixtureSandbox(IMAGE)


@pytest.mark.asyncio
async def test_closed_input_and_fixed_boundary(
    runner: sandbox.FixtureSandbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    commands: list[tuple[str, ...]] = []

    async def command(args: tuple[str, ...], timeout: float) -> sandbox._CommandResult:
        commands.append(args)
        operation = args[3]
        output = b""
        if operation == "start":
            output = b"untrusted test failure"
        if operation == "inspect":
            output = b'{"Status":"exited","ExitCode":1,"OOMKilled":false,"Error":""}'
        return sandbox._CommandResult(1 if operation == "start" else 0, output)

    monkeypatch.setattr(sandbox, "_command", command)
    with pytest.raises(ValueError):
        await runner.run("../../secret")
    with pytest.raises(ValueError):
        sandbox.FixtureSandbox("python:latest")
    assert not commands
    result = await runner.run("clamp-v1")
    assert result.status == "tests_failed" and result.cleanup_confirmed
    assert result.output == "untrusted test failure"
    create = commands[0]
    for flag in (
        "--pull=never",
        "--network=none",
        "--read-only",
        "--user=65532:65532",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges:true",
        "--memory=128m",
        "--memory-swap=128m",
        "--cpus=0.5",
        "--pids-limit=32",
        "--log-driver=none",
    ):
        assert flag in create
    assert not any(
        arg.startswith(("--mount", "--volume", "--env", "--privileged")) for arg in create
    )
    assert create[-5:] == (IMAGE, "-I", "-B", "/opt/runner.py", "clamp-v1")
    assert [args[3] for args in commands] == ["create", "start", "inspect", "rm", "ps"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode", ("create", "start", "timeout", "overflow", "cleanup", "uncertain_create")
)
async def test_failure_timeout_overflow_and_uncertain_cleanup(
    runner: sandbox.FixtureSandbox, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    commands: list[str] = []

    async def command(args: tuple[str, ...], timeout: float) -> sandbox._CommandResult:
        operation = args[3]
        commands.append(operation)
        if operation == "create" and mode == "uncertain_create":
            return sandbox._CommandResult(-1, b"", timeout=True)
        if operation == mode or (mode == "cleanup" and operation == "ps"):
            return sandbox._CommandResult(1, b"sensitive daemon diagnostic")
        if operation == "start":
            return sandbox._CommandResult(
                -1, b"bounded", timeout=mode == "timeout", limit=mode == "overflow"
            )
        if operation == "inspect":
            return sandbox._CommandResult(0, b'{"Status":"created","ExitCode":0}')
        return sandbox._CommandResult(0, b"")

    monkeypatch.setattr(sandbox, "_command", command)
    if mode in ("cleanup", "uncertain_create"):
        with pytest.raises(sandbox.SandboxError, match="^sandbox_cleanup_unconfirmed:"):
            await runner.run("clamp-v1")
    else:
        result = await runner.run("clamp-v1")
        assert result.status == {
            "timeout": "timeout",
            "overflow": "output_limit",
        }.get(mode, "infrastructure_error")
        assert "sensitive" not in result.model_dump_json()
    assert commands[-2:] == ["rm", "ps"]


@pytest.mark.asyncio
async def test_cancellation_waits_for_owned_cleanup(
    runner: sandbox.FixtureSandbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    started, removing, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    commands: list[str] = []

    async def command(args: tuple[str, ...], timeout: float) -> sandbox._CommandResult:
        operation = args[3]
        commands.append(operation)
        if operation == "start":
            started.set()
            await asyncio.Event().wait()
        if operation == "rm":
            removing.set()
            await release.wait()
        return sandbox._CommandResult(0, b"")

    monkeypatch.setattr(sandbox, "_command", command)
    task = asyncio.create_task(runner.run("timeout-v1"))
    await asyncio.wait_for(started.wait(), 1)
    task.cancel()
    await asyncio.wait_for(removing.wait(), 1)
    task.cancel()  # A second cancellation cannot abandon cleanup.
    await asyncio.sleep(0)
    assert not task.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert commands == ["create", "start", "rm", "ps"]


@pytest.mark.asyncio
async def test_command_bounds_real_pipes_and_deadlines() -> None:
    # Trusted test programs exercise the CLI transport, never repository code.
    import sys

    overflow = await asyncio.wait_for(
        sandbox._command((sys.executable, "-c", "import os; os.write(1, b'x' * 200000)"), 2),
        3,
    )
    assert overflow.limit and len(overflow.output) == sandbox.OUTPUT_LIMIT
    timed = await asyncio.wait_for(
        sandbox._command((sys.executable, "-c", "import time; time.sleep(10)"), 0.1), 3
    )
    assert timed.timeout
