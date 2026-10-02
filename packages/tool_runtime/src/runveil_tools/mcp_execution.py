"""Captured public MCP server source and conservative local implementation identity."""

import hashlib
import json
import sys
from collections.abc import Awaitable, Callable
from importlib.metadata import version
from pathlib import Path

from mcp import StdioServerParameters
from mcp.client.stdio import DEFAULT_INHERITED_ENV_VARS
from runveil_core import mcp as contracts
from runveil_core import models, tools
from runveil_core.mcp import MCP_TOOL, McpIdentity
from runveil_core.tools import FixtureInput, FixtureOutput, Permission, SideEffect, TypedTool

from runveil_tools import mcp as adapter


def _implementation_digest() -> str:
    sources = [Path(__file__).read_bytes(), sys.version.encode()]
    for module in (contracts, models, tools, adapter):
        assert module.__file__ is not None
        sources.append(Path(module.__file__).read_bytes())
    for package in ("mcp", "pydantic", "pydantic-core", "anyio", "jsonschema"):
        sources.append(f"{package}={version(package)}".encode())
    return hashlib.sha256(b"\0".join(sources)).hexdigest()


_IMPLEMENTATION_DIGEST = _implementation_digest()


class PinnedMcpFixture:
    def __init__(self) -> None:
        # Execute captured source, not a server file reopened after identity checks.
        self._source = Path(__file__).with_name("mcp_fixture.py").read_text(encoding="utf-8")
        if len(self._source.encode()) > 65_536:
            raise ValueError("MCP fixture source exceeds its limit")
        self._server = StdioServerParameters(
            command=str(Path(sys.executable).absolute()),
            args=["-I", "-c", self._source],
            env=dict.fromkeys(DEFAULT_INHERITED_ENV_VARS, ""),
            cwd=str(Path(sys.executable).resolve().parent),
        )
        executable = Path(sys.executable)
        interpreter = {
            "command": self._server.command,
            "resolved": str(executable.resolve()),
            "binary": hashlib.sha256(executable.read_bytes()).hexdigest(),
            "prefix": sys.prefix,
            "version": sys.version,
            "flags": ["-I", "-c"],
            "environment": self._server.env,
            "cwd": str(self._server.cwd),
        }
        contract = {
            "local": MCP_TOOL,
            "remote": "info",
            "input": FixtureInput.model_json_schema(),
            "output": FixtureOutput.model_json_schema(),
            "timeout_seconds": 10.0,
            "permission": "read",
            "side_effect": "read_only",
        }
        self.identity = McpIdentity(
            interpreter_digest=hashlib.sha256(
                json.dumps(interpreter, sort_keys=True).encode()
            ).hexdigest(),
            server_digest=hashlib.sha256(self._source.encode()).hexdigest(),
            implementation_digest=_IMPLEMENTATION_DIGEST,
            contract_digest=hashlib.sha256(
                json.dumps(contract, sort_keys=True).encode()
            ).hexdigest(),
        )

    def binding(
        self, admit: Callable[[], Awaitable[None]]
    ) -> TypedTool[FixtureInput, FixtureOutput]:
        async def invoke(arguments: FixtureInput) -> FixtureOutput:
            await admit()
            async with adapter.connect_read_tools(self._server) as connection:
                remote = connection.bind(
                    remote_name="info",
                    name=MCP_TOOL,
                    description="Read fixed public Runveil metadata over MCP.",
                    input_type=FixtureInput,
                    output_type=FixtureOutput,
                )
                await admit()
                return await remote.handler(arguments)

        return TypedTool(
            name=MCP_TOOL,
            description="Read fixed public Runveil metadata over MCP.",
            input_type=FixtureInput,
            output_type=FixtureOutput,
            handler=invoke,
            permission=Permission.READ,
            side_effect=SideEffect.READ_ONLY,
        )
