# ADR 0041: Pinned read-only MCP worker recovery

- Status: Accepted for Phase 11B implementation; review pending
- Date: 2026-10-02

## Decision

Add one explicit `mcp-fixture-read-v1` profile and configuration/checkpoint version 17. It reads a fixed project-owned public metadata server using Phase 11A's official
SDK adapter. There is no user-selected executable, command, environment, transport
or remote catalog. The independent Phase 11A embedding API remains available.

The immutable version retains four SHA-256 digests: interpreter launch identity,
captured server source, selected tool contract and implementation. Interpreter
identity includes absolute/resolved executable paths and bytes, Python version and
prefix, isolated-mode arguments, fixed working directory and environment. Contract
identity includes local/remote names, schemas, timeout and classification. Covered
implementation includes the binding, MCP adapter, core MCP/model/tool source,
worker source, Python version and MCP/Pydantic/pydantic-core/AnyIO/jsonschema
versions. Paths, arguments and environment values themselves are not persisted.

Submission captures identity without launching a server. Every clean start/resume
reconstructs the binding and compares the complete expected configuration in the
existing fenced store start, before history writes or model/tool dispatch. MCP
configuration requires the dedicated claimed profile and an expected configuration;
generic unclaimed execution is refused. No migration; old configurations remain
readable. The trace reader recognizes version 17 using its existing projection.

## Dispatch and recovery

Clean execution requires separate `--allow-read`. Version 17 requires the fixed
MCP READ policy and disables retries. Native offer filtering, dual-grant dispatch,
strict contracts and cooperative deadlines remain unchanged. The profile inherits
elapsed, token, synthetic cost, repeated-tool and invocation limits, with three
steps, two model calls, one tool call and a one-hour run deadline. The deadline
exceeds the 660-second lease so real restart recovery can occur after lease expiry.
Successful
fixture accounting is 20 input/10 output tokens and 50,000 nano-USD, not real billing.

The typed handler lazily opens MCP after committed tool intent. Before launch and
again after discovery, the worker fences ownership and checks RUNNING state, exact
pending tool/arguments, event tail and deadline. Transactions end before I/O. These
are admission checks, not atomic revocation of an admitted RPC. Existing outcome
fences reject stale results. Existing tool telemetry surrounds startup through
cleanup and correlates by durable invocation ID.

Python runs in isolated mode with captured source through `-c`, avoiding a server
file reopen after hashing. SDK-inherited environment keys are explicitly blanked;
the working directory is fixed. No credential or argument overrides. The Phase 11A
fault-mode server remains separate from this worker's server.

Clean recovery uses durable context: after a model checkpoint, execute the recorded
tool once; after a tool checkpoint, finish without launching MCP again. Active
leases and terminal duplicates select no work. Before constructing a binding, the
worker checks for requested model/tool records. For unresolved intent it passes
the pinned configuration and no registry to existing recovery validation. Core
atomically fails as `execution_interrupted`, or existing elapsed expiry when overdue.
No binding construction, discovery, RPC, retry or READ grant is needed for that
terminal-only path. A remote response lost before persistence is still uncertain.
Ambiguous/corrupt history is rejected, never guessed or replayed.

## Limits

Trusted local host code only. This conservative identity is not dependency-byte
attestation, immutable deployment or a sandbox. Operators must keep interpreter
and installed imports stable during execution. Relocating the environment or
changing covered source, even formatting, rejects clean recovery. Do not rewrite
immutable versions to adopt drift. Captured server text stays stable within a binding.

Ownership loss during discovery prevents the tool RPC. Loss after admission may
allow the read but cannot commit under the stale claim. SDK wire-decoding and
cleanup limits from ADR 0040 remain. Missing grants/configuration rejection leave
the current lease in place, as in other bound profiles; retry after expiry with the
correct setup. No renewal service, quarantine policy, broker integration, cleanup
reconciler, transport expansion, mutation or approval extension. Existing patch
approvals cannot authorize MCP calls.

Tests use a real SDK server, deterministic interruption at commit boundaries,
fresh worker processes for clean recovery and lease expiry during discovery/after
response. Phase 5's separate actual-SIGKILL acceptance is rerun; this slice does not
claim a new MCP process-death harness.
