"""Operator-only, disposable Docker fixture runner; not a registered agent tool."""

import argparse
import asyncio
import json
import os
import re
import shutil
import sys
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from runveil_core.fixtures import FIXTURE_PATHS
from runveil_core.models import Contract

FIXTURES = (*FIXTURE_PATHS, "boundary-v1", "timeout-v1", "output-v1")
OUTPUT_LIMIT = 16_384
CONTROL_TIMEOUT = 15.0
EXECUTION_TIMEOUT = 15.0


class SandboxResult(Contract):
    policy: Literal["docker-fixture-v1"] = "docker-fixture-v1"
    image: str
    fixture: str
    container: str
    status: Literal["passed", "tests_failed", "timeout", "output_limit", "infrastructure_error"]
    exit_code: int | None = None
    output: str = ""
    cleanup_confirmed: bool


class SandboxError(Exception):
    """Fixed diagnostic only; never carries Docker stderr or host configuration."""


class _AdmissionStopped(Exception):
    def __init__(self, cause: Exception) -> None:
        self.cause = cause


@dataclass(frozen=True)
class _CommandResult:
    code: int
    output: bytes
    limit: bool = False
    timeout: bool = False


async def _command(
    args: tuple[str, ...], timeout: float, data: bytes | None = None
) -> _CommandResult:
    # Do not inherit Docker context, remote endpoints, TLS settings or API overrides.
    process = await asyncio.create_subprocess_exec(
        *args,
        stdin=asyncio.subprocess.PIPE if data is not None else asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env={"PATH": os.defpath},
    )

    async def send() -> None:
        assert process.stdin is not None and data is not None
        try:
            process.stdin.write(data)
            await process.stdin.drain()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            process.stdin.close()

    sender = asyncio.create_task(send()) if data is not None else None
    output = bytearray()
    try:
        async with asyncio.timeout(timeout):
            assert process.stdout is not None
            while chunk := await process.stdout.read(min(4096, OUTPUT_LIMIT + 1 - len(output))):
                output.extend(chunk)
                if len(output) > OUTPUT_LIMIT:
                    return _CommandResult(-1, bytes(output[:OUTPUT_LIMIT]), limit=True)
            if sender is not None:
                await sender
            return _CommandResult(await process.wait(), bytes(output))
    except TimeoutError:
        return _CommandResult(-1, bytes(output), timeout=True)
    finally:
        if sender is not None:
            sender.cancel()
            with suppress(asyncio.CancelledError):
                await sender
        if process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
        # Drain after killing the CLI so a full pipe cannot deadlock wait().
        assert process.stdout is not None
        while await process.stdout.read(4096):
            pass
        await process.wait()


class FixtureSandbox:
    def __init__(self, image: str, *, socket: Path = Path("/var/run/docker.sock")) -> None:
        if re.fullmatch(r"sha256:[0-9a-f]{64}", image) is None:
            raise ValueError("An immutable local image ID is required")
        if not socket.is_absolute() or not socket.is_socket():
            raise ValueError("A local Unix Docker socket is required")
        docker = shutil.which("docker")
        if docker is None:
            raise SandboxError("sandbox_unavailable")
        self.image = image
        self._docker = (docker, "--host", "unix://" + str(socket))

    def _create(
        self, name: str, fixture: str, inspection: bool = False, patch: bool = False
    ) -> tuple[str, ...]:
        return (
            *self._docker,
            "create",
            "--pull=never",
            *(("--interactive",) if patch else ()),
            "--name",
            name,
            "--label",
            "runveil.sandbox=docker-fixture-v1",
            "--network=none",
            "--read-only",
            "--user=65532:65532",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges:true",
            "--cpus=0.5",
            "--memory=128m",
            "--memory-swap=128m",
            "--pids-limit=32",
            "--ulimit=nofile=64:64",
            "--ulimit=core=0:0",
            "--restart=no",
            "--log-driver=none",
            "--ipc=none",
            "--tmpfs=/workspace:rw,noexec,nosuid,nodev,size=16m,mode=0700,uid=65532,gid=65532",
            "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=8m,mode=0700,uid=65532,gid=65532",
            "--workdir=/workspace",
            "--entrypoint=/usr/local/bin/python3",
            self.image,
            "-I",
            "-B",
            "/opt/runner.py",
            fixture,
            *(("inspect",) if inspection else ("apply",) if patch else ()),
        )

    async def _cleanup(self, name: str) -> bool:
        try:
            await _command((*self._docker, "rm", "--force", "--volumes", name), CONTROL_TIMEOUT)
            remaining = await _command(
                (*self._docker, "ps", "-aq", "--filter", f"name=^/{name}$"), CONTROL_TIMEOUT
            )
            return remaining.code == 0 and not remaining.output.strip()
        except OSError:
            return False

    async def run(
        self,
        fixture: str,
        *,
        inspection: bool = False,
        patch_input: bytes | None = None,
        invocation_id: UUID | None = None,
        admit: Callable[[], Awaitable[None]] | None = None,
    ) -> SandboxResult:
        if (
            fixture not in FIXTURES
            or ((inspection or patch_input is not None) and fixture not in FIXTURE_PATHS)
            or (inspection and patch_input is not None)
            or (patch_input is not None and len(patch_input) > 32768)
        ):
            raise ValueError("Unknown project fixture")
        name = "runveil-sandbox-" + (invocation_id or uuid4()).hex
        result = SandboxResult(
            image=self.image,
            fixture=fixture,
            container=name,
            status="infrastructure_error",
            cleanup_confirmed=False,
        )
        # Admission failure before create owns no resource and needs no cleanup.
        if admit is not None:
            await admit()
        uncertain_create = True
        try:
            created = await _command(
                self._create(name, fixture, inspection, patch_input is not None), CONTROL_TIMEOUT
            )
            uncertain_create = created.timeout or created.limit
            if created.code == 0:
                if admit is not None:
                    try:
                        await admit()
                    except Exception as exc:
                        # Keep storage/ownership failures out of Docker error normalization.
                        raise _AdmissionStopped(exc) from None
                if patch_input is None:
                    attached = await _command(
                        (*self._docker, "start", "--attach", name), EXECUTION_TIMEOUT
                    )
                else:
                    attached = await _command(
                        (*self._docker, "start", "--attach", "--interactive", name),
                        EXECUTION_TIMEOUT,
                        patch_input + b"\n",
                    )
                if attached.limit or attached.timeout:
                    result = result.model_copy(
                        update={
                            "status": "output_limit" if attached.limit else "timeout",
                            "output": attached.output.decode(
                                "utf-8",
                                errors="strict"
                                if inspection or patch_input is not None
                                else "replace",
                            ),
                        }
                    )
                else:
                    state = await _command(
                        (*self._docker, "inspect", "--format", "{{json .State}}", name),
                        CONTROL_TIMEOUT,
                    )
                    if state.code == 0:
                        data = json.loads(state.output)
                        code = data.get("ExitCode")
                        if (
                            data.get("Status") == "exited"
                            and not data.get("OOMKilled")
                            and not data.get("Error")
                            and type(code) is int
                            and code in (0, 1, 124)
                            and attached.code == code
                        ):
                            result = result.model_copy(
                                update={
                                    "status": {0: "passed", 1: "tests_failed", 124: "timeout"}[
                                        code
                                    ],
                                    "exit_code": code,
                                    "output": attached.output.decode(
                                        "utf-8",
                                        errors="strict"
                                        if inspection or patch_input is not None
                                        else "replace",
                                    ),
                                }
                            )
        except _AdmissionStopped as exc:
            raise exc.cause from None
        except (OSError, ValueError, TypeError, AttributeError):
            # Infrastructure diagnostics can include sensitive host configuration.
            pass
        finally:
            cleanup = asyncio.create_task(self._cleanup(name))
            cancelled = False
            while not cleanup.done():
                try:
                    await asyncio.shield(cleanup)
                except asyncio.CancelledError:
                    cancelled = True
            confirmed = cleanup.result()
            if not confirmed or uncertain_create:
                raise SandboxError("sandbox_cleanup_unconfirmed:" + name)
            if cancelled:
                raise asyncio.CancelledError
        return result.model_copy(update={"cleanup_confirmed": True})


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True, help="Reviewed local sha256 image ID")
    parser.add_argument("--fixture", choices=FIXTURES, required=True)
    parser.add_argument("--socket", type=Path, default=Path("/var/run/docker.sock"))
    args = parser.parse_args()
    try:
        result = await FixtureSandbox(args.image, socket=args.socket).run(args.fixture)
    except SandboxError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except (ValueError, OSError):
        print("sandbox_configuration_invalid", file=sys.stderr)
        return 2
    # JSON escapes control characters in untrusted test output; no raw terminal logs.
    print(result.model_dump_json(indent=2))
    return 0 if result.status == "passed" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        raise SystemExit(130) from None
