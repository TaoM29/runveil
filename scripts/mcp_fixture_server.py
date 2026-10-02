"""Public offline MCP fixture, with explicit fault modes for boundary verification."""

import argparse
import asyncio
import os

from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from runveil_core.tools import FixtureInput, FixtureOutput


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario",
        choices=(
            "success",
            "error",
            "invalid",
            "oversized",
            "wait",
            "disconnect",
            "drift",
            "paginated",
            "malformed",
        ),
        default="success",
    )
    scenario = parser.parse_args().scenario
    if scenario == "malformed":
        print("private-sentinel malformed wire data", flush=True)
    server = Server("runveil-public-fixture")

    @server.list_tools()  # type: ignore[no-untyped-call, untyped-decorator]
    async def list_tools(request: types.ListToolsRequest) -> types.ListToolsResult:
        tools = [
            types.Tool(
                name="info",
                description="Remote description is not authority or a model instruction.",
                inputSchema=FixtureInput.model_json_schema(),
                outputSchema=(
                    {"type": "object"} if scenario == "drift" else FixtureOutput.model_json_schema()
                ),
                annotations=types.ToolAnnotations(readOnlyHint=False, destructiveHint=True),
            )
        ]
        return types.ListToolsResult(
            tools=tools, nextCursor="private-sentinel" if scenario == "paginated" else None
        )

    @server.call_tool(validate_input=False)  # type: ignore[untyped-decorator]
    async def call_tool(name: str, arguments: dict[str, object]) -> types.CallToolResult:
        if scenario == "wait":
            await asyncio.Event().wait()
        if scenario == "disconnect":
            os._exit(0)
        if scenario == "error":
            return types.CallToolResult(
                isError=True, content=[types.TextContent(type="text", text="private-sentinel")]
            )
        result = FixtureOutput().model_dump(mode="json")
        if scenario == "invalid":
            result["fixture_version"] = "private-sentinel"
        return types.CallToolResult(
            content=[types.TextContent(type="text", text="x" * 65_536)]
            if scenario == "oversized"
            else [],
            structuredContent=result,
        )

    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
