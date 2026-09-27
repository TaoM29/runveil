# Minimal runtime operations

The Phase 4A runtime executes a new QUEUED run in the calling Python process. It has no HTTP
endpoint or worker. Migrate PostgreSQL and export `DATABASE_URL` using the README
quickstart, then run:

```sh
uv run python scripts/runtime_demo.py
```

This **writes** one new agent, immutable version and run per invocation. It uses a
scripted provider, makes no network model call, and prints the run UUID, terminal
status, consumed steps and public fixture summary. Database records are retained.
The script reads the final checkpoint back through a separate session to verify
reconstruction. It does not migrate, reset or clean the database.

## Embedding

Create a version-2 `RuntimeConfig` from `runveil_core.runtime` with an explicit
`tool_policy`; persist its
`model_dump(mode="json")` as an agent version through `AgentRepository`. Create a
run pinned to that version. Instantiate `PostgresExecutionStore` with an
`async_sessionmaker`, then call:

```python
from runveil_core.tools import Permission, ToolPolicy, fixture_registry

policy = ToolPolicy(allowed_tools=("fixture.info",), permissions=(Permission.READ,))
# Also set tool_policy=policy on the RuntimeConfig before persisting its version.
state = await execute(
    run.id,
    "Identify the public fixture.",
    provider_name="scripted",
    provider=provider,
    store=PostgresExecutionStore(sessions),
    tools=fixture_registry(),
    tool_policy=policy,
)
```

The provider name must match the pinned configuration. Supply a `ModelProvider`
implementation and manage its lifetime outside the loop (including closing HTTP
providers). This binding is trusted operator configuration, not automatic provider
discovery or authentication. The demo is a complete runnable embedding example.

Configuration schema version 2 includes `provider`, `model`, `system_prompt`,
`max_steps` (1–64, default 8), `temperature`, `max_output_tokens` and
`timeout_seconds`, plus `tool_policy` (allowed tool names and permissions). Credentials and endpoint configuration belong outside it.
Version 1 and existing opaque configurations are rejected before lifecycle writes;
create a new immutable agent version to opt into explicit grants. Historical
checkpoints remain readable. Invalid
configuration, task or provider binding is rejected before lifecycle writes.

`max_steps` counts model and tool invocations together. The normal demonstration
uses three: model → tool → model finish. A finish at the limit succeeds; an action
requiring another invocation beyond the limit fails with `step_limit_exceeded`.
The start and limit-failure checkpoints are bookkeeping, so persisted step-row
count can exceed consumed invocation count. There is no retry or context compaction.

Only explicitly granted registered tools are advertised. The built-in `fixture.info`
is available through `fixture_registry()`. Its arguments must be `{}` and its output is
`{"project": "Runveil", "fixture_version": 1}`. It reads no user files and has no
shell or network access. Tool results enter the next model context as labelled tool
messages. The hosted adapter's existing mapping treats these as untrusted data.

## Tool contracts and policy

`TypedTool` binds a name/description, strict `Contract` input/output model types,
async handler, permission, side-effect class and deadline. `ToolRegistry` rejects
duplicate names and has no registration mutation API. Schemas derive from the same
Pydantic types used at dispatch; extra fields, scalar coercion and non-finite values
are rejected. Input and output JSON are each limited to 64 KiB (UTF-8 of the
standard JSON encoding, including escaping). Invalid/oversized output is discarded
before context or persistence. Definitions expose output schema and a `never` retry
policy; no retry is attempted.

`RuntimeConfig.tool_policy` pins the version's grant ceiling. `execute(tool_policy=...)`
provides the independent operator grant ceiling, and `tools` supplies trusted native
bindings. A tool name and its permission must be in **both** policies. Omitting any
of these capabilities defaults to no tool access. Only READ with PURE or READ_ONLY
classification is allowed, even if other permissions are explicitly granted.
Offers are filtered and direct registry dispatch checks again. Unadvertised model
names fail as `invalid_response`; direct registry calls distinguish `tool_unavailable`
and `tool_permission_denied`. A model action can never extend either grant list.

Handlers must be cooperative async application code. The deadline cannot interrupt
blocking Python or isolate a handler that ignores cancellation. These classifications
and grants are an application boundary, not an OS sandbox or authentication system.
Repository filesystem access remains Phase 4B. Mutation approval remains Phase 6.
Operator code and implementation bindings are not stored in checkpoints; future
recovery needs an implementation-version policy before replay.

## Evidence and failure handling

The run's current lifecycle is authoritative. Ordered history contains start,
model/tool requested/outcome, checkpoint and lifecycle events. Invocation records
retain normalized requests/responses, safe errors, and tool-to-model provenance.
`load_runtime_state(session, run_id)` validates the latest checkpoint's inner
runtime schema and returns conversation, consumed steps, final result and error.
Read lifecycle separately: a terminal checkpoint is recorded at RUNNING revision,
with the terminal transition immediately after it in the same transaction.
Malformed or unsupported checkpoint state is rejected, not treated as empty.

Known provider errors, timeouts and invalid actions become failed model outcomes;
unexpected provider exceptions become `provider_unavailable` without raw details.
Tool failures use `invalid_tool_arguments`, `invalid_tool_output`, `tool_timeout`
or `tool_failed`, without raw exception details. Tool requests commit before handler
execution outside database transactions; failures become failed tool outcomes. Each failure outcome and
FAILED transition commits atomically. Invalid response content is not retained.
Valid task/conversation/action content **is persisted**: callers must exclude
secrets and hidden reasoning. Persistence is not an arbitrary-content redactor.

Database failures and stale revision/history conflicts propagate. Do not blindly
retry `execute`. Task cancellation propagates and can leave RUNNING/REQUESTED
records. Another actor may cancel a run during generation; its late result cannot
be committed, although the remote call may have happened or been billed. This
runtime starts queued runs only: no recovery, replay, leases or exactly-once claim.
Reconstruction of evidence does not resume work. Phase 5 owns durable recovery.

The Phase 2 hosted live acceptance gate was closed by a separate user-reported
invocation; see [the evidence](PHASE_2B.md#subsequent-hosted-live-acceptance--complete).
Running this offline demo is not hosted acceptance evidence.
