# ADR 0035: Single-use approved sandbox patch and validation

- Status: Accepted for Phase 10D
- Date: 2026-10-02

## Decision

Add `sandbox-patch-v1` with configuration/checkpoint version 14. New runs use the
existing fixed clamp inspection/proposal pause, but pin WRITE as well as READ and
EXECUTE. Their approval explicitly permits application and validation in a fresh
disposable fixture. Version-13 review-only approvals cannot be adopted. The local
operator separately grants `--allow-write` and `--allow-execute` at dispatch.

After approval, core obtains the exact proposal and original full inspection from
a fenced persistence boundary, commits one `repository.apply_patch` intent, and
invokes a narrow bound sandbox writer. Reuse the existing database single-use
mutation index. Revalidate profile, approval/provenance, exact intent, operator
permissions, lease/history and deadline before create and before start. Docker I/O
remains outside transactions. This is admission fencing, not atomic Docker revocation.

Transport bounded JSON through stdin, never host mounts, shell interpolation,
model-selected commands or environment. In the pinned image, reconstruct the three
fixed fixture files and compare the complete workspace and exact clamp.py preimage
before replacing that file atomically. Run fixed unittest arguments in a separate
process with bounded output/time, stop its process group, and revalidate all three
files after tests. Persist approved diff, before/after workspace digests and bounded
test observations only after confirmed container cleanup and final database fences.
The workspace is disposable; retained durable evidence is the patch artifact.

A valid applied outcome records both successful and failed test observations.
Failed tests/timeouts/output limits terminate the task as validation failure while
preserving evidence that the approved patch was applied inside the container.
Malformed/incomplete results, postimage drift or infrastructure loss do not prove a
known mutation outcome. An unresolved mutation intent terminates as
`sandbox_patch_outcome_unknown`, without constructing a Docker adapter or replaying.
No automatic rollback, second mutation or adoption of apparent filesystem state.

## Limits

One public controlled clamp fixture and a scripted repair; no multi-task coding or
model-quality claim. Container/daemon/image trust and existing host isolation,
resource, cleanup and operator recovery limits remain. Tests execute proposed code
only inside the container; test output and pass/fail are observations, not a proof
against malicious code or a hostile multi-tenant guarantee. No persistent checkout,
API/UI expansion, provider calls, new dependency or schema migration. Host patch
version 11 retains its existing independent transaction and recovery contract.
