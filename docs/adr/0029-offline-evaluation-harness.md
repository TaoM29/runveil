# ADR 0029: Offline deterministic evaluation foundation

- Status: Accepted for Phase 8A
- Date: 2026-10-01

## Decision

Add a cohesive `runveil_evaluations` adapter package above the existing core,
persistence and read-tool adapters. Execute a bounded, versioned development suite
through ordinary PostgreSQL-backed runtime runs. Two immutable agent versions
vary only the step budget. Each case gets a fresh scripted provider and private
fixture directory with one explicitly allowlisted file. No model-selected code,
shell, mutation, approval decision or network provider is added. Existing job
enrollment and claims fence each new run under the dedicated `eval-calibration-v1`
profile, preserving durable elapsed/token/cost/call limits. Standard workers do not
select that profile; this slice exposes no resume or polling command.

Frozen EvalSuite/EvalCase contracts include tasks, fixture content, ordered scripted
responses and exact oracles. Canonical content digests identify the entire benchmark,
including scoring version; a version label alone cannot establish equivalence.
Score only reconstructed terminal database evidence: successful runtime completion,
exact final summary and exact ordered successful tool calls. Runtime failures and
oracle mismatches remain distinct. Every scheduled case stays in the denominator.

EvalRun/EvalCaseResult snapshots and a paired comparison are exported as one
exclusive-create local JSON report, with the complete suite, immutable agent
configuration/identity, runtime source/dependency fingerprint, timestamps and durable
run IDs. Reports are local artifacts, not new evaluation database tables or a
resumable scheduler. Infrastructure exceptions abort the batch without emitting a
complete report; already committed execution evidence remains in PostgreSQL. No
automatic retries or recovery of uncertain work are introduced.

## Scope and trade-offs

Three public code-reading calibration cases establish repeatable scoring and a
known step-budget regression. Scripts contain the answers: this measures the
harness, not model capability. The charter's approximately 20–30 controlled coding
cases, held-out split, broader agent/provider selection and full Phase 8 acceptance
remain a subsequent slice. Running arbitrary generated tests safely belongs with
the planned sandbox boundary, not an evaluator subprocess escape hatch.

Reports use persisted request-intent counts, steps, retries, checkpoint token/cost
accounting (with explicit unknown components) and persisted elapsed time. Timing,
UUIDs and timestamps are not deterministic; scores and counts are reproducible.
Synthetic scripted token usage and tariffs are labelled and are not invoices.
Comparisons require identical suite content, ordered case coverage and implementation
fingerprint. No confidence intervals, significance claims or Phase 9 statistics.

Existing runtime durability, authorization, telemetry and API/UI remain unchanged.
Reports contain only public fixtures plus selected metadata and safe classifications;
raw database URLs, filesystem roots and exception text are never exported. Local
reports are evidence, not signed attestations or a general sensitive-data scrubber.
