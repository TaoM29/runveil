# Offline evaluation (Phases 8A–8B)

Run from the repository root after the [development setup](DEVELOPMENT.md), with
`DATABASE_URL` pointing at a migrated local PostgreSQL database:

```sh
uv run python -m runveil_evaluations --output /tmp/runveil-evaluation.json
```

The command above preserves the original three-case calibration. Phase 8B also
provides a versioned 24-case code-reading corpus, selected one partition at a time:

```sh
uv run python -m runveil_evaluations --suite code-reading --output /tmp/code-reading-development.json
uv run python -m runveil_evaluations --suite code-reading --split held-out --output /tmp/code-reading-held-out.json
```

Development has 16 cases (32 runtime runs); held-out has 8 (16 runtime runs).
Expected pass counts are 8/16 → 16/16 and 4/8 → 8/8 respectively. Each report retains
its selected split and complete denominator. No merged score is produced. Unsupported
suite/split choices fail before output or database creation. The calibration suite
has no held-out split. See the [inventory, rationales and split discipline](BENCHMARK.md).

The output path must not exist. The original calibration creates one agent, two immutable
versions and six ordinary durable runs with existing job claims under the dedicated
`eval-calibration-v1` profile. It executes sequentially with no hosted provider,
approval decisions, shell execution or writes to your
checkout. Each case gets a fresh temporary `example.py` and the existing native
read/search adapter with an exact one-file allowlist and READ-only policy.
Temporary fixture directories are removed after execution.

Expected calibration: the three-step baseline passes **2/3**, the five-step
candidate **3/3**. The search/read case requires five model/tool steps and fails
at the baseline's step limit. The other two cases finish within both budgets.
A complete comparison exits zero even when cases fail: case failure is evaluation
evidence. Infrastructure/configuration/output failures exit one with a fixed safe
message; they do not masquerade as scored runtime failures or a complete batch.

The report includes:

- Full versioned selected suite and split, including task, public fixture, script and oracle.
- Canonical SHA-256 suite identity covering all content and the scoring version.
- Separate EvalRun IDs, persisted agent-version IDs/numbers and full configurations.
- Source/dependency fingerprint covering core, persistence, tools and evaluator,
  Python and relevant library versions; provider/model are in each configuration.
- Every case's durable run ID, terminal status, event watermark, grade and safe error.
- Intent counts, consumed steps, retries, reported tokens and estimated nano-USD,
  including unknown-attempt counters, plus persisted elapsed milliseconds.
- Aggregate counts and success rates with the same complete case denominator and
  the candidate-minus-baseline rate delta. No statistical significance claim.

Scoring reads a consistent read-only database snapshot after execution. Passing
requires successful completion, exact summary equality (no whitespace or case
normalization), and the exact ordered successful tool names specified by the case.
Runtime failures, wrong summaries and wrong tool sequences are separate categories.
Comparisons reject changed benchmark content, implementation or ordered case coverage,
reused execution IDs and identical agent-version IDs. Final response text and raw
invocation payloads are not copied into case results. Use a run ID with the existing
[authenticated trace console](TRACES.md) while the database is retained.

## Reproducibility and limits

This is a **scripted calibration**, not a measurement of model quality. Scripts
already contain the expected answers. Token counts and the pinned price are
synthetic; sums are known subtotals when unknown counters are nonzero. Persisted
elapsed time includes storage overhead and is not provider latency. IDs, timestamps
and timing vary between executions; grades, intent counts and accounting reproduce
under unchanged implementation and fixtures.

Reports are local JSON artifacts, not database EvalRun rows, signed evidence or a
resumable batch scheduler. Execution rows/checkpoints remain authoritative. An
interrupted command can leave an empty/partial output file and committed runs;
validate the JSON report before using it, retain failed-run evidence, and use a new
output path for a fresh batch. No uncertain invocation is replayed automatically.
The implementation fingerprint detects source changes during a batch but is not a
supply-chain attestation; database/server/OS differences can still affect timing.

Only the built-in public suites are exposed through the CLI. No file/plugin grader
loader, arbitrary provider configuration or code execution is supported. The larger
corpus supplies 24 controlled code-reading cases and a public reserved partition;
it is not a secret or contamination-free held-out model assessment. Broader provider
selection remains future work; [Phase 8 acceptance](PHASE_8.md) closes the documented
scripted scope. Opt-in [statistical summaries](STATISTICS.md) are implemented in Phase 9A,
and sandboxed execution is Phase 10. See [ADR 0029](../adr/0029-offline-evaluation-harness.md)
and [ADR 0030](../adr/0030-controlled-code-reading-benchmark.md).

## Report verification boundary

Schema parsing checks shape and types. Recompute a retained comparison with `compare`
to check suite/implementation/coverage/identity compatibility and aggregates; this
still trusts its case grades and metadata and is not authentication of imported JSON.
No untrusted report-import endpoint is provided. Authoritative score verification
requires the original database records; temporary acceptance databases are removed
after inspection. See the [closure audit](PHASE_8.md) for evidence and claim limits.

Use `--statistics` for a separately versioned wrapper containing paired uncertainty,
elapsed/cost summaries and failure categories. Default output stays unchanged.
See the [methodology and limitations](STATISTICS.md) before interpreting bounds.

## Tool-name expectations

`EvalCase.expected_tools` accepts the shared validated tool-name contract. The
scorer compares ordered native durable tool records, including MCP records, without
transport-specific logic. Expectations do not register or authorize tools: the
CLI runner still uses only its fixed repository read/search registry and READ
policy. Phase 11 verifies MCP scoring against an already-completed pinned worker
run; it does not introduce an MCP benchmark runner. Frozen suite content and
digests are unchanged. See the [acceptance audit](PHASE_11.md).
