"""Pinned identity and grants for the fixed read-only MCP worker."""

from typing import Annotated

from pydantic import Field

from runveil_core.models import Contract
from runveil_core.tools import Permission, ToolPolicy

MCP_PROFILE = "mcp-fixture-read-v1"
MCP_TOOL = "mcp.fixture.info"
MCP_POLICY = ToolPolicy(allowed_tools=(MCP_TOOL,), permissions=(Permission.READ,))
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class McpIdentity(Contract):
    interpreter_digest: Digest
    server_digest: Digest
    implementation_digest: Digest
    contract_digest: Digest
