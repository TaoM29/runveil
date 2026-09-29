# Minimal runtime operations

The unclaimed embedding executes a new, unenrolled QUEUED run in the calling Python
process. Phase 5A adds a separate [durable fixture worker](WORKER.md) with leases,
validated checkpoint resume and conservative interruption failure. There is no
HTTP execution endpoint. Migrate PostgreSQL and export `DATABASE_URL` using the README
quickstart, then run:

```sh
uv run python scripts/runtime_demo.py
```

This **writes** one new agent, immutable version and run per invocation. It uses a
scripted provider and a temporary public repository fixture, makes no network
model call, and prints the run UUID, terminal status, consumed steps and summary.
It exercises search → read → finish in five invocations, then removes its temporary
fixture directory. See [repository tools](REPOSITORY_TOOLS.md) for binding and limits. Database records are retained.
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
uses five: model → search → model → read → model finish. A finish at the limit succeeds; an action
requiring another invocation beyond the limit fails with `step_limit_exceeded`.
The start, retry-resume and limit-failure checkpoints are bookkeeping, so persisted
step-row count can exceed consumed invocation count. Version-2 configurations keep
retries disabled. Version 3 adds `model_retry` (`max_retries`, `base_delay_seconds`)
and requires a worker claim when retries are enabled. The opt-in operator grant
and durable scheduling rules are documented in [worker operations](WORKER.md).
Configuration version 4 additionally requires `max_elapsed_seconds` (1–86400)
and a worker claim. Its immutable deadline starts at first execution and includes
retry waits/restarts. Expiry yields a persisted `elapsed_time_exceeded` failure;
see [worker operations](WORKER.md#durable-elapsed-time-budget) for admission,
timeout and lease limits. Versions 2/3 have no elapsed budget.

Version 5 additionally requires run-wide `max_input_tokens` and
`max_total_output_tokens`, and records token accounting in checkpoints. These are
post-attempt reported-usage thresholds; incomplete usage stops continuation.
See [worker operations](WORKER.md#durable-reported-token-budgets) for failure,
recovery and overshoot semantics. Versions 2–4 retain their prior behavior.

Version 6 requires `pricing` and `max_cost_nanousd`, alongside version-5 budgets.
Pricing must be a complete matching linear USD snapshot; unknown pricing is an
invalid configuration, never implicit zero. Cost estimates use exact integer
nano-USD and retain unknown-usage counts. See
[worker operations](WORKER.md#pinned-pricing-and-cost-limits).

Version 7 additionally requires `max_identical_tool_calls` (1–64). The PostgreSQL
store enforces this per tool name/structural JSON arguments using durable intent
history before tool dispatch. No counter is reset by retries or checkpoints; see
[worker operations](WORKER.md#repeated-tool-limit).

Version 8 additionally requires `max_model_calls` and `max_tool_calls` (0–64).
They count committed intents across the run, including failed/uncertain attempts;
zero disables that invocation kind. The combined `max_steps` still applies. See
[worker operations](WORKER.md#separate-model-and-tool-call-limits).
There is no context compaction.

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
Repository filesystem access uses the separate [native adapter](REPOSITORY_TOOLS.md)
with an explicit root/file allowlist and bounded reads. Mutation approval remains Phase 6.
Operator code and implementation bindings are not stored in checkpoints. Version 9
requires a `workspace` with root, content and implementation SHA-256 fingerprints,
alongside all version-8 budgets. Earlier versions cannot carry that identity.
Workspace-bound execution requires `PostgresExecutionStore(expected_config=...)`
constructed from the actual binding; omission or mismatch refuses start/resume.
The fixed `repository-read-v1` worker reconstructs and verifies a snapshot before
execution; see [worker operations](WORKER.md#pinned-repository-recovery).

## Evidence and failure handling

The run's current lifecycle is authoritative. Ordered history contains start,
model/tool requested/outcome, checkpoint and lifecycle events. Invocation records
retain normalized requests/responses, safe errors, and tool-to-model provenance.
`load_runtime_state(session, run_id)` validates the latest checkpoint's inner
runtime schema and returns conversation, consumed steps, final result and error.
Version-2 snapshots retain the next tool action and source model ID. Version-3
snapshots additionally retain the run-wide retry count and failed model source ID.
Version-4 snapshots use the same conversation/retry fields with an immutable
deadline on the worker job; the start step records that deadline. Version-1
snapshots remain readable for inspection.
Read lifecycle separately: a terminal checkpoint is recorded at RUNNING revision,
with the terminal transition immediately after it in the same transaction.
Malformed or unsupported checkpoint state is rejected, not treated as empty.

Known provider errors, timeouts and invalid actions become failed model outcomes;
unexpected provider exceptions become `provider_unavailable` without raw details.
Tool failures use `invalid_tool_arguments`, `invalid_tool_output`, `tool_timeout`
or `tool_failed`, without raw exception details. Native repository handlers also
use fixed resource unavailable/limit/invalid codes and file-policy denial. Tool requests commit before handler
execution outside database transactions; failures become failed tool outcomes. Terminal failure outcomes and
FAILED transitions commit atomically. An explicitly eligible model retry instead
commits its failed outcome, schedule and RETRYING transition atomically. Invalid response content is not retained.
Valid task/conversation/action content **is persisted**: callers must exclude
secrets and hidden reasoning. Persistence is not an arbitrary-content redactor.

Database failures and stale revision/history conflicts propagate. Do not blindly
retry `execute`. Task cancellation propagates and can leave RUNNING/REQUESTED
records. Another actor may cancel a run during generation; its late result cannot
be committed, although the remote call may have happened or been billed. The
unclaimed embedding starts queued runs only. `load_runtime_state` is inspection,
not recovery. The [worker](WORKER.md) resumes enrolled supported runs under a live
claim; uncertain invocations fail without replay. Neither path claims exactly-once
external execution.

The Phase 2 hosted live acceptance gate was closed by a separate user-reported
invocation; see [the evidence](PHASE_2B.md#subsequent-hosted-live-acceptance--complete).
Running this offline demo is not hosted acceptance evidence.
