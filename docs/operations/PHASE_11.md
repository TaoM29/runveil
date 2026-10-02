# Phase 11 acceptance and closure assessment

Date: 2026-10-02. Assessed after Phase 11B; **ready for closure review within trusted local read-only scope**.

The [original charter](../PROJECT_PLAN.md) requires an MCP adapter, discovery,
schema normalization, invocation and permissions. This audit uses those requirements
and accepted [ADR 0040](../adr/0040-typed-read-only-mcp.md) and
[ADR 0041](../adr/0041-pinned-mcp-worker.md), rather than substituting handoff claims.
Current verification and the closure change are recorded in [Phase 11C](PHASE_11C.md).

## Original acceptance criteria

| Criterion                                                                     | Evidence and scope                                                                                                                                                                                                                                                                    | Assessment                                                                                                   |
| ----------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| At least one MCP server exposes a tool through the existing runtime           | The public SDK stdio server exposes `info`, bound as `mcp.fixture.info`. Both the persisted demonstration and pinned v17 worker use the native registry and execution loop. Real SDK/PostgreSQL tests verify the output, originating model record, atomic outcome and restored state. | Met for the public read-only fixture.                                                                        |
| MCP tools appear exactly like native tools to authorization/evaluation layers | Native `TypedTool`, `ToolRegistry`, READ classification and intersected pinned/operator grants apply. The unchanged evaluator scores terminal MCP records, ordered tool names and accounting; a wrong expected tool produces `tool_mismatch`.                                         | Met after removing the evaluator oracle's repository-only name restriction. Expectations grant no authority. |

## Original implementation checklist

| Requirement          | Implementation and evidence                                                                                                                                                                                                                                                                                          |
| -------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| MCP client adapter   | Official locked Python MCP SDK 1.30, context-managed stdio client/session; project-owned runtime retains dispatch and state transitions.                                                                                                                                                                             |
| Discovery            | Requires tools capability; one complete catalog page, at most 128 entries and 64 KiB decoded data; duplicate names, pagination and setup failures refuse usable bindings. Deadline and lifecycle checks bound cooperative work.                                                                                      |
| Schema normalization | Operator-selected remote tool maps to strict local input/output contracts and local `mcp.*` name/description. Exact discovered/local schema equality is required, including titles/defaults. Remote annotations do not assign permissions. This is explicit contract mapping, not arbitrary JSON Schema translation. |
| Invocation           | Native strict input validation precedes remote execution; deadlines, cancellation, bounded decoded output and strict structured-result validation apply. Remote errors/disconnects become fixed safe native errors; no raw server errors enter persisted results.                                                    |
| Permissions          | Both pinned policy and execution-time operator policy must grant READ and the local tool name. The registry controls advertisement/dispatch; discovery does not authorize a call. Only READ_ONLY bindings are supported.                                                                                             |

## Cross-cutting boundary review

- **Durability:** tool intent commits before worker server launch/RPC. Native stores
  retain model provenance and atomically write outcome, event, step and checkpoint.
  Network/process I/O occurs outside database transactions. Dedicated claimed-store
  admission and expected configuration comparison are required for the MCP profile.
- **Recovery:** v17 pins interpreter, captured server source, selected contract and
  implementation identity. Clean model/tool checkpoints resume in a fresh process
  without repeating committed work; changed identity refuses dispatch. Requested
  model/tool intent, including a remote response lost before commit, fails without
  constructing a binding, launching a server or replaying. Elapsed expiry retains
  precedence. Active/terminal duplicates do not execute again.
- **Ownership:** admission checks claim/history/deadline before connection and after
  discovery. Ownership loss during discovery prevents RPC; loss after response
  prevents stale persistence. A subsequent owner handles uncertainty without replay.
- **Telemetry:** native model/tool/root spans and durable run/step/invocation/tool
  identifiers remain correlated. Trace projection recognizes v17 accounting.
  Structured output remains ordinary tool evidence; telemetry excludes payloads,
  credentials and raw SDK errors. Stderr and malformed-line parser output are suppressed.
- **Approvals:** MCP v17 has no approval state or mutation capability. Existing
  patch/sandbox approvals validate their own profiles and cannot authorize MCP.
  Remote tool annotations, descriptions and evaluator expectations cannot elevate
  authority. Existing approval tests remain in the regression suite.
- **Evaluation:** only oracle name validation changed, to the shared bounded `Name`
  contract. Scoring still consumes native persisted evidence. The evaluation CLI
  retains its fixed repository registry and policy; this is not a new MCP suite
  runner. Frozen benchmark content/digests and scoring semantics remain unchanged.

## Focused verification completion

The storage issue that interrupted closure verification is resolved. The focused
rerun passed all 20 MCP tests and all 11 Docker regression cases, plus sandbox
boundary acceptance. Cleanup checks confirmed no remaining review containers,
volume, network, image tag or temporary test databases. No implementation changes
were needed. See [the recovery and rerun record](PHASE_11C.md#storage-recovery-and-focused-rerun).
These Docker checks exercise the existing sandbox, not isolation of MCP host code.

## Closure decision and limits

All five original checklist items and both acceptance criteria are demonstrated
within the accepted trusted local read-only scope. No remaining closure blocker was
identified. Recommend human acceptance of Phase 11; this assessment is not sign-off
or authorization to begin Phase 12.

Stdio executes trusted host code, not a sandbox. SDK decoding precedes application
size checks; these are not hard wire-memory or CPU limits. Identity is conservative
compatibility evidence, not full dependency attestation; deployments must remain
stable during execution. Admission cannot revoke an already-started RPC. The worker
supports only its pinned public fixture; other servers need a separately reviewed
profile. In-process bindings do not gain worker recovery automatically.

MCP recovery evidence uses deterministic cancellation at durable boundaries,
actual SDK calls and fresh-process clean recovery. There is no MCP-specific SIGKILL
harness; existing Phase 5 real process-death acceptance is separate regression
evidence. No HTTP transport, reconnect/retry, arbitrary schema interpreter, remote
service, hosted model or mutation is required for this closure. No general model
quality or hostile-server isolation claim is made.

Stop for review. No commit or push.
