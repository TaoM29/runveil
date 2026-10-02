# MCP tools: Phase 11

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
- The in-process demo has no worker enrollment, resume, reconnect or retry. An interrupted run
  remains inspectable with unresolved intent and cannot be restarted by this demo.
  Use the separate pinned worker below for supported recovery; do not attach MCP
  bindings to other worker profiles.
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

## Pinned durable fixture worker: Phase 11B

`mcp-fixture-read-v1` supports clean checkpoint recovery with conservative refusal
of uncertain intent. Server source, remote `info`, local `mcp.fixture.info` and
schemas are fixed project code. There are no executable, environment or transport
flags. Use the same migrated database and Python environment for both commands:

```sh
uv run python -m runveil_worker.mcp_worker submit
# Use the run_id printed above:
RUNVEIL_TELEMETRY=json uv run python -m runveil_worker.mcp_worker work --run-id <uuid> --allow-read
```

Submission atomically records version-17 configuration and enrollment without
starting MCP. Clean work requires its own READ grant and verifies interpreter,
server, contract and implementation digests against the pinned version before
execution. The server launches only inside a committed typed tool attempt;
ownership and deadline are rechecked after discovery, before RPC. The ten-second
tool deadline includes startup/discovery. Run limits are three steps, two model
calls, one tool call and one elapsed hour, allowing recovery after the 660-second
lease expires. Accounting is synthetic fixture usage.

Normal output contains `selected: true`, no error, and `Public MCP fixture verified.`.
Exit status is zero for success/no selection, one for run/setup failure and 130 for
keyboard interruption. Active leases and terminal duplicates select no work. The
existing trace surface shows version-17 accounting and ordinary tool records.

After interruption, wait for the PostgreSQL lease to expire (660 seconds after its
last fence), then rerun work. Do not edit lease rows operationally. Clean checkpoints
resume without repeating persisted observations. Unresolved model/tool intent fails
as `execution_interrupted` without constructing a binding or launching MCP, even
without `--allow-read`. Existing elapsed-expiry handling takes precedence when
overdue. There is no reconnect, automatic retry or guess about a lost RPC result.

Interpreter path/bytes, environment prefix, server source, schemas or covered
implementation changes reject clean recovery. Keep the original deployment
available, or submit a new run for changed code. Missing grants or configuration
rejection leave the lease until expiry. Identity is not protection against hostile
installations or concurrent replacement of installed imports. MCP worker verification
for this slice runs on macOS; CI is configured for Linux. Windows is unverified.

The server uses isolated Python arguments, a fixed directory and blanked SDK-inherited
environment keys. Captured public source is supplied via `-c`; secrets/arbitrary
scripts are not accepted. No host filesystem/network isolation or MCP mutations.
Native patch approvals grant no authority here.

```sh
uv run pytest packages/persistence/tests/test_mcp_worker.py
```

Eight cases cover grants/store guards and identity drift at a clean checkpoint;
fresh-process recovery after model/tool checkpoints; unresolved model/tool intent
and a lost response; duplicate selection; and ownership loss during discovery and
after response. All protocol dispatch uses the real SDK fixture. See
[ADR 0041](../adr/0041-pinned-mcp-worker.md) and [handoff](PHASE_11B.md).

## Acceptance and closure

The [Phase 11 audit](PHASE_11.md) records acceptance within this trusted read-only
scope, with [current verification and handoff](PHASE_11C.md). Human review is pending.
Native evaluation scoring accepts MCP tool names and persisted evidence; oracle
expectations do not grant capabilities or change the fixed evaluation runner.
