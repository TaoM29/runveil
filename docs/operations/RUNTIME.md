# Minimal runtime operations

Phase 3 executes a new QUEUED run in the calling Python process. It has no HTTP
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

Create a `RuntimeConfig` from `runveil_core.runtime`; persist its
`model_dump(mode="json")` as an agent version through `AgentRepository`. Create a
run pinned to that version. Instantiate `PostgresExecutionStore` with an
`async_sessionmaker`, then call:

```python
state = await execute(
    run.id,
    "Identify the public fixture.",
    provider_name="scripted",
    provider=provider,
    store=PostgresExecutionStore(sessions),
)
```

The provider name must match the pinned configuration. Supply a `ModelProvider`
implementation and manage its lifetime outside the loop (including closing HTTP
providers). This binding is trusted operator configuration, not automatic provider
discovery or authentication. The demo is a complete runnable embedding example.

Configuration schema version 1 includes `provider`, `model`, `system_prompt`,
`max_steps` (1–64, default 8), `temperature`, `max_output_tokens` and
`timeout_seconds`. Credentials and endpoint configuration belong outside it.
Existing opaque agent configurations are not automatically made executable. Invalid
configuration, task or provider binding is rejected before lifecycle writes.

`max_steps` counts model and tool invocations together. The normal demonstration
uses three: model → tool → model finish. A finish at the limit succeeds; an action
requiring another invocation beyond the limit fails with `step_limit_exceeded`.
The start and limit-failure checkpoints are bookkeeping, so persisted step-row
count can exceed consumed invocation count. There is no retry or context compaction.

Only `fixture.info` is advertised. Its arguments must be `{}` and its output is
`{"project": "Runveil", "fixture_version": 1}`. It reads no user files and has no
shell or network access. Tool results enter the next model context as labelled tool
messages. The hosted adapter's existing mapping treats these as untrusted data.
Typed registries, per-tool permissions, approvals and sandbox tools remain future work.

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
Invalid fixture arguments become a failed tool outcome. Each failure outcome and
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
