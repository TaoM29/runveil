"""Verified adapter binding for the single durable clamp test profile."""

import hashlib
import json
import sys
from collections.abc import Awaitable, Callable
from importlib import import_module
from importlib.metadata import version
from pathlib import Path
from uuid import UUID

from runveil_core.sandbox import SandboxIdentity, TestsResult
from runveil_core.tools import ToolError, ToolErrorCode

from runveil_tools.sandbox import FixtureSandbox, SandboxError


class BoundSandbox:
    def __init__(self, image: str, *, socket: Path = Path("/var/run/docker.sock")) -> None:
        if not socket.is_absolute():
            raise ValueError("A local absolute Docker socket is required")
        endpoint = socket.resolve(strict=True)
        self._runner = FixtureSandbox(image, socket=endpoint)
        stat = endpoint.stat()
        implementation = hashlib.sha256(b"runveil-sandbox-execution-v1\0")
        for name in (
            "runveil_tools.sandbox",
            "runveil_tools.sandbox_execution",
            "runveil_core.sandbox",
            "runveil_core.runtime",
            "runveil_core.tools",
            "runveil_core.models",
        ):
            path = import_module(name).__file__
            if path is None:
                raise ValueError("Sandbox execution requires source-backed modules")
            implementation.update(name.encode() + b"\0" + Path(path).read_bytes())
        implementation.update(sys.version.encode() + version("pydantic").encode())
        self.identity = SandboxIdentity(
            image=image,
            endpoint_digest=hashlib.sha256(
                json.dumps([str(endpoint), stat.st_dev, stat.st_ino]).encode()
            ).hexdigest(),
            implementation_digest=implementation.hexdigest(),
        )

    async def run(self, invocation_id: UUID, admit: Callable[[], Awaitable[None]]) -> TestsResult:
        try:
            result = await self._runner.run(
                self.identity.fixture, invocation_id=invocation_id, admit=admit
            )
        except SandboxError:
            # The owned name is derivable from the persisted tool invocation UUID.
            raise ToolError(ToolErrorCode.CLEANUP_UNCONFIRMED) from None
        if result.status == "infrastructure_error":
            raise ToolError(ToolErrorCode.RESOURCE_UNAVAILABLE)
        return TestsResult.model_validate(
            {
                "status": result.status,
                "exit_code": result.exit_code,
                "output": result.output[:4096],
                "output_truncated": len(result.output) > 4096 or result.status == "output_limit",
            }
        )
