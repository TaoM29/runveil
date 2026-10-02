"""Operator-selected MCP read tools bound to existing native contracts."""

import asyncio
import json
import logging
import os
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from datetime import timedelta

from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client
from runveil_core.models import Contract
from runveil_core.tools import (
    MAX_TOOL_BYTES,
    Permission,
    SideEffect,
    ToolError,
    ToolErrorCode,
    TypedTool,
)


class McpReadTools:
    """A session-scoped catalog; binding is an operator assertion of read-only behavior."""

    def __init__(self, session: ClientSession, catalog: dict[str, types.Tool]) -> None:
        self._session = session
        self._catalog = catalog
        self._active = True

    def bind[Input: Contract, Output: Contract](
        self,
        *,
        remote_name: str,
        name: str,
        description: str,
        input_type: type[Input],
        output_type: type[Output],
        timeout_seconds: float = 10.0,
    ) -> TypedTool[Input, Output]:
        remote = self._catalog.get(remote_name)
        if (
            not self._active
            or not name.startswith("mcp.")
            or remote is None
            or remote.inputSchema != input_type.model_json_schema()
            or remote.outputSchema != output_type.model_json_schema()
        ):
            raise ToolError(ToolErrorCode.RESOURCE_INVALID)

        async def invoke(arguments: Input) -> Output:
            if not self._active:
                raise ToolError(ToolErrorCode.UNAVAILABLE)
            result = await self._session.call_tool(
                remote_name, arguments=arguments.model_dump(mode="json")
            )
            if result.isError:
                raise ToolError(ToolErrorCode.FAILED)
            try:
                if (
                    len(result.model_dump_json().encode("utf-8")) > MAX_TOOL_BYTES
                    or result.structuredContent is None
                ):
                    raise ValueError("Unsupported MCP result")
                return output_type.model_validate_json(
                    json.dumps(result.structuredContent, allow_nan=False), strict=True
                )
            except Exception:
                raise ToolError(ToolErrorCode.INVALID_OUTPUT) from None

        return TypedTool(
            name=name,
            description=description,
            input_type=input_type,
            output_type=output_type,
            handler=invoke,
            permission=Permission.READ,
            side_effect=SideEffect.READ_ONLY,
            timeout_seconds=timeout_seconds,
        )


@contextmanager
def _quiet_transport_logs() -> Iterator[None]:
    # The SDK logs malformed wire payloads with exception details. Suppress only
    # this connection's task context, without changing unrelated logger levels.
    active = ContextVar("runveil_mcp_transport", default=False)

    class Filter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            return not active.get()

    logger = logging.getLogger("mcp.client.stdio")
    transport_filter = Filter()
    token = active.set(True)
    logger.addFilter(transport_filter)
    try:
        yield
    finally:
        logger.removeFilter(transport_filter)
        active.reset(token)


@asynccontextmanager
async def connect_read_tools(
    server: StdioServerParameters, *, discovery_timeout_seconds: float = 10.0
) -> AsyncIterator[McpReadTools]:
    """Launch trusted operator code; this transport is not a process sandbox."""
    if not 0 < discovery_timeout_seconds <= 60:
        raise ValueError("Discovery timeout must be between zero and sixty seconds")
    entered = False
    try:
        async with _connect(server, discovery_timeout_seconds) as connection:
            entered = True
            yield connection
    except Exception:
        if entered:
            raise
        # SDK task groups can wrap startup errors, including executable/env details.
        raise ToolError(ToolErrorCode.RESOURCE_UNAVAILABLE) from None


@asynccontextmanager
async def _connect(
    server: StdioServerParameters, discovery_timeout_seconds: float
) -> AsyncIterator[McpReadTools]:
    # Server stderr must not enter application logs or durable execution evidence.
    with _quiet_transport_logs(), open(os.devnull, "w") as stderr:
        async with stdio_client(server, errlog=stderr) as (read, write):
            async with ClientSession(
                read, write, read_timeout_seconds=timedelta(seconds=600)
            ) as session:
                try:
                    async with asyncio.timeout(discovery_timeout_seconds):
                        initialized = await session.initialize()
                        if initialized.capabilities.tools is None:
                            raise ToolError(ToolErrorCode.RESOURCE_INVALID)
                        page = await session.list_tools()
                        if (
                            page.nextCursor is not None
                            or len(page.tools) > 128
                            or len(page.model_dump_json().encode("utf-8")) > MAX_TOOL_BYTES
                            or len({tool.name for tool in page.tools}) != len(page.tools)
                        ):
                            raise ToolError(ToolErrorCode.RESOURCE_LIMIT)
                except TimeoutError:
                    raise ToolError(ToolErrorCode.TIMEOUT) from None
                except ToolError:
                    raise
                except Exception:
                    raise ToolError(ToolErrorCode.RESOURCE_INVALID) from None
                connection = McpReadTools(session, {tool.name: tool for tool in page.tools})
                try:
                    yield connection
                finally:
                    connection._active = False
