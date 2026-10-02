"""Fixed public server for the durable MCP read profile; no operator-selected actions."""

import asyncio

from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from runveil_core.tools import FixtureInput, FixtureOutput


async def main() -> None:
    server = Server("runveil-durable-public-fixture")

    @server.list_tools()  # type: ignore[no-untyped-call, untyped-decorator]
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name="info",
                description="Read fixed public fixture metadata.",
                inputSchema=FixtureInput.model_json_schema(),
                outputSchema=FixtureOutput.model_json_schema(),
            )
        ]

    @server.call_tool(validate_input=False)  # type: ignore[untyped-decorator]
    async def call_tool(name: str, arguments: dict[str, object]) -> types.CallToolResult:
        if name != "info" or arguments:
            return types.CallToolResult(isError=True, content=[])
        return types.CallToolResult(
            content=[], structuredContent=FixtureOutput().model_dump(mode="json")
        )

    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
