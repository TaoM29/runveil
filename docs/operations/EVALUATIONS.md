# Offline evaluation calibration (Phase 8A)

Run from the repository root after the [development setup](DEVELOPMENT.md), with
`DATABASE_URL` pointing at a migrated local PostgreSQL database:

```sh
uv run python -m runveil_evaluations --output /tmp/runveil-evaluation.json
```

The output path must not exist. The command creates one agent, two immutable
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

- Full versioned development suite, including task, public fixture, script and oracle.
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

Only the built-in public suite is exposed through the CLI. No file/plugin grader
loader, arbitrary provider configuration, code execution or held-out dataset is
supported. The approximately 20–30 controlled coding cases and broader version
selection remain future Phase 8 work; statistical uncertainty is Phase 9, and
sandboxed execution is Phase 10. See [ADR 0029](../adr/0029-offline-evaluation-harness.md).
