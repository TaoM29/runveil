# Phase 10 acceptance and closure assessment

Date: 2026-10-02. Assessed after Phase 10G; **ready for closure review in the bounded scripted scope**.

The [original charter](../PROJECT_PLAN.md) requires a software-engineering agent
with fixtures, a disposable Docker workspace, inspection, search, test execution,
patching, diff, approval and a final result. This audit preserves those requirements
rather than treating earlier handoffs as a replacement specification.

## Original acceptance criteria

| Criterion                                               | Evidence and scope                                                                                                                                                                                                                                                                                                                                                                       | Assessment                                                                       |
| ------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| Agent solves several controlled coding tasks end to end | Clamp bounds, whitespace normalization and fractional means each inspect and search the pinned snapshot, reproduce a failing baseline, produce an exact proposal, wait for human approval, apply in a new sandbox and pass fixed post-change tests. Separate fresh CLI processes verify durable continuation. Exact replacement and postimage oracles include unchanged task/test files. | Demonstrated for three public scripted fixtures. No general model-quality claim. |
| Failed tasks remain inspectable                         | Local inspection covers queued and pre-approval failures, rejected proposals, failed post-change validation and uncertain mutation outcomes. It retains ordered tool observations, error codes, approval, exact diff and test evidence. Deterministic recovery checks refuse replay.                                                                                                     | Met in this bounded workflow.                                                    |
| No arbitrary host execution                             | Fixture Python is executed only by the fixed image runner in disposable containers with no host mounts/network, a read-only root and bounded tmpfs/resources/output. Closed task selection supplies no command, environment or arbitrary path. Host tests read fixture text but never import/execute it.                                                                                 | Met under the documented trusted Docker daemon/image boundary.                   |

The retained [10G six-run evidence](evidence/phase10g/tasks.json) contains search,
approval and rejection flows for every fixture; [boundary evidence](evidence/phase10g/boundary.json)
contains isolation, failing baseline, watchdog, output and cancellation probes.
The fresh-process acceptance checks independent search path/line and inspection
identity oracles, exact proposal/postimage and unchanged task/test files. Search
recovery and forged outcome/context checks run against PostgreSQL; both v15 and v16
exercise WRITE denial and uncertain-effect recovery without replay.
The [10F ineffective mean repair](evidence/phase10f/failed-validation.json) remains
retained evidence of applied-but-failed validation under explicit provider fault
injection; the shared mutation path and its validation-boundary tests remain in the
full regression suite. The [10G handoff](PHASE_10G.md) records current checks.

## Original implementation checklist

| Requirement                 | Current state                                                                                                                                                                                                                                                      |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Repository fixtures         | Three distinct, versioned, project-owned coding tasks; separate isolation probes.                                                                                                                                                                                  |
| Disposable Docker workspace | Fresh pinned image/container for inspection, baseline and mutation; no surviving checkout.                                                                                                                                                                         |
| File inspection             | Complete bounded task-specific snapshot; independent fixture binding and exact preimage validation.                                                                                                                                                                |
| Search                      | Version-16 workflow searches the complete immutable sandbox snapshot with literal bounded queries, digest/path/line/excerpt results, READ authorization and durable provenance revalidation. Results drive the scripted source selection before baseline/proposal. |
| Test execution              | Fixed baseline and post-change unittest commands, bounded output/time and retained outcomes.                                                                                                                                                                       |
| Patching                    | One approved source replacement; full workspace/preimage revalidation, single-use durable intent and independent container target allowlist.                                                                                                                       |
| Diff                        | Canonical approved before/after with deterministic unified diff and verified postimage digest.                                                                                                                                                                     |
| Approval                    | Exact proposal digest/revision; explicit approval pause and separate execution-time WRITE/EXECUTE; no automatic approval in product flows.                                                                                                                         |
| Final result                | Durable success only after approved application and passing validation; known failed validation retains mutation evidence; uncertain outcomes never claim success.                                                                                                 |

## Closure decision and limits

All nine implementation checklist items and all three acceptance criteria are
now demonstrated within the documented controlled fixture scope. Recommend Phase 10
closure after human review. No general-purpose autonomous coding claim or Phase 11
continuation is implied. Earlier v15 runs remain supported by their original CLI;
new search-enabled tasks use v16. Search uses saved original sandbox evidence, not
a live filesystem or post-change snapshot. Full workspace/preimage revalidation
still occurs inside the mutation container before any replacement.

The fixtures and repair table are public integration demonstrations, not an unseen
benchmark or independent assessment of a language model. A scripted repair proves
workflow mechanics, not autonomous diagnosis across arbitrary repositories. Fixed
test success does not prove correctness against malicious proposed code. Docker
shares a kernel; image/daemon trust, admission-not-revocation semantics and manual
cleanup after crashes remain as in ADRs 0032–0035. No paid provider, remote broker,
API/UI approval expansion or arbitrary host execution was introduced.

Stop for review. No commit or push.
