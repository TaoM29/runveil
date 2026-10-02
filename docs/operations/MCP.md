# MCP tools: Phase 11A

The stdio adapter exposes explicitly selected read tools through the same
`TypedTool` and `ToolRegistry` used by native tools. See
[ADR 0040](../adr/0040-typed-read-only-mcp.md) for the scope and trust boundary.

## Offline persisted demonstration

Use Python 3.12, the locked workspace install and a migrated PostgreSQL database
from the [development guide](DEVELOPMENT.md). No model key or external service is
used. Each invocation creates a new agent/version/run in `DATABASE_URL`.

```sh
uv sync --locked --all-packages
uv run alembic upgrade head
uv run python scripts/mcp_demo.py
# Optional existing payload-free telemetry:
RUNVEIL_TELEMETRY=json uv run python scripts/mcp_demo.py
```

Expected output is a run ID, `status=SUCCEEDED` and `steps=3`. The script starts
`scripts/mcp_fixture_server.py` with the current interpreter and closes the SDK
session/process afterward. The server exposes `info`; the registered local name
is `mcp.fixture.info`. Empty arguments produce the strict public metadata object
`{"project":"Runveil","fixture_version":1}`. A scripted provider selects it and
finishes. The run retains ordinary model/tool records, provenance, events and a
restorable checkpoint. Inspect its ID using the existing authenticated
[trace surface](TRACES.md). Telemetry retains its existing worker service label.

## Binding another trusted read tool

Embedding code owns `StdioServerParameters` and enters `connect_read_tools` in the
same async task that will close it. Call `connection.bind` with a remote name,
local `mcp.*` name, local description and strict `Contract` input/output classes.
Schemas must exactly equal the discovered input/output schemas; even a title or
default difference rejects the binding. Put the returned binding into an ordinary
`ToolRegistry` and supply READ plus its local name in both run and operator policy.
The demo is the complete executable example.

Startup/discovery has a default ten-second cooperative deadline, configurable up
to sixty seconds. One page, 128 tools and 64 KiB of decoded catalog are the limits.
Missing capabilities, incomplete catalogs or setup failures do not return usable
bindings. Missing/mismatched selected schemas reject registration. Tool deadlines
default to ten seconds and use the native maximum of 600 seconds.

Only `structuredContent` is retained, after strict local validation. The complete
decoded response, including ignored content, must fit 64 KiB. Remote `isError`,
disconnect and SDK validation errors become `tool_failed`; native deadlines become
`tool_timeout`; unsupported/oversized decoded results become `invalid_tool_output`.
No raw server error is persisted. Startup failures use `tool_resource_unavailable`.
The SDK may ignore malformed unsolicited lines; their raw parse logs are suppressed.

The fixture's `--scenario` options exist solely for deterministic boundary tests.
They include remote failure, invalid output, oversized content, blocking calls,
disconnect, schema drift, pagination and malformed unsolicited output.

## Operational limits

- Only trusted local server executables. Stdio is host execution and provides no
  filesystem/network isolation. Server hints are not evidence of read-only behavior.
- The SDK inherits its minimal default environment even with `env={}`; explicitly
  passed credentials remain operator memory/configuration. Do not put secrets in
  command arguments, model arguments, descriptions or output contracts.
- Wire decoding occurs before size checks. This is not an adversarial-server memory
  or CPU isolation boundary. The SDK owns shutdown and process termination.
- No HTTP transport or server-selected sampling, resources, prompts or approval
  actions. No automatic registration or list-change refresh.
- No worker enrollment, resume, reconnect or retry. An interrupted in-process run
  remains inspectable with unresolved intent and cannot be restarted by this demo.
  Do not attach MCP bindings to existing worker profiles to imply recovery support.
- No MCP mutation support. Existing patch approvals cannot authorize MCP tools.

## Verification

```sh
uv run pytest packages/tool_runtime/tests/test_mcp.py
# Requires RUNVEIL_TEST_DATABASE_URL with CREATEDB:
uv run pytest packages/persistence/tests/test_mcp_execution.py
```

These tests launch the real official-SDK stdio fixture. Adapter tests cover native
grants/validation, schema rejection, safe failures, deadline/cancellation, discovery
limits, log redaction and expired bindings. Database tests verify committed intent
outside transactions, source-model provenance, atomic/restorable outcomes, durable
trace and telemetry correlation, and refusal to replay interrupted execution.
