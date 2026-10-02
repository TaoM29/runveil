# Phase 10 acceptance and closure assessment

Date: 2026-10-02. Assessed after Phase 10F; **Phase 10 remains open**.

The [original charter](../PROJECT_PLAN.md) requires a software-engineering agent
with fixtures, a disposable Docker workspace, inspection, search, test execution,
patching, diff, approval and a final result. This audit preserves those requirements
rather than treating earlier handoffs as a replacement specification.

## Original acceptance criteria

| Criterion                                               | Evidence and scope                                                                                                                                                                                                                                                                                                                               | Assessment                                                                       |
| ------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------- |
| Agent solves several controlled coding tasks end to end | Clamp bounds, whitespace normalization and fractional means each reproduce a failing baseline, produce an exact proposal, wait for human approval, apply in a new sandbox and pass fixed post-change tests. Separate fresh CLI processes verify durable continuation. Exact replacement and postimage oracles include unchanged task/test files. | Demonstrated for three public scripted fixtures. No general model-quality claim. |
| Failed tasks remain inspectable                         | Local inspection covers queued and pre-approval failures, rejected proposals, failed post-change validation and uncertain mutation outcomes. It retains ordered tool observations, error codes, approval, exact diff and test evidence. Deterministic recovery checks refuse replay.                                                             | Met in this bounded workflow.                                                    |
| No arbitrary host execution                             | Fixture Python is executed only by the fixed image runner in disposable containers with no host mounts/network, a read-only root and bounded tmpfs/resources/output. Closed task selection supplies no command, environment or arbitrary path. Host tests read fixture text but never import/execute it.                                         | Met under the documented trusted Docker daemon/image boundary.                   |

The retained [six-run evidence](evidence/phase10f/tasks.json) contains approval and
rejection flows for every fixture; [boundary evidence](evidence/phase10f/boundary.json)
contains isolation, failing baseline, watchdog, output and cancellation probes.
A separate [ineffective mean repair](evidence/phase10f/failed-validation.json) records
confirmed application with failed tests and a retained task failure, under explicit
provider fault injection. The [10F handoff](PHASE_10F.md) records exact checks and remaining limits. Existing
[10D validation tests](../../packages/persistence/tests/test_sandbox_patch_worker.py) cover applied-but-failed
validation; [10E recovery checks](PHASE_10E.md) cover interrupted workflow effects.

## Original implementation checklist

| Requirement                 | Current state                                                                                                                                                                                                                                     |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Repository fixtures         | Three distinct, versioned, project-owned coding tasks; separate isolation probes.                                                                                                                                                                 |
| Disposable Docker workspace | Fresh pinned image/container for inspection, baseline and mutation; no surviving checkout.                                                                                                                                                        |
| File inspection             | Complete bounded task-specific snapshot; independent fixture binding and exact preimage validation.                                                                                                                                               |
| Search                      | **Open.** Version-15 workflow exposes inspect, tests and proposal before approval, not search. Phase 4's host `repository.search` is not a sandbox binding and is not dispatched by this workflow. Full-file inspection is not counted as search. |
| Test execution              | Fixed baseline and post-change unittest commands, bounded output/time and retained outcomes.                                                                                                                                                      |
| Patching                    | One approved source replacement; full workspace/preimage revalidation, single-use durable intent and independent container target allowlist.                                                                                                      |
| Diff                        | Canonical approved before/after with deterministic unified diff and verified postimage digest.                                                                                                                                                    |
| Approval                    | Exact proposal digest/revision; explicit approval pause and separate execution-time WRITE/EXECUTE; no automatic approval in product flows.                                                                                                        |
| Final result                | Durable success only after approved application and passing validation; known failed validation retains mutation evidence; uncertain outcomes never claim success.                                                                                |

## Closure decision and limits

The multi-task gate is evidenced within the existing scripted scope. Full Phase 10
closure is **not ready** because bounded search is still missing from the software
workflow. Keep that gap explicit; no charter exception or Phase 11 continuation is
implied. Recommended next slice: integrate bounded search over the pinned sandbox
evidence, verify authorization, bounds, provenance and recovery, then repeat this
checklist for closure review.

The fixtures and repair table are public integration demonstrations, not an unseen
benchmark or independent assessment of a language model. A scripted repair proves
workflow mechanics, not autonomous diagnosis across arbitrary repositories. Fixed
test success does not prove correctness against malicious proposed code. Docker
shares a kernel; image/daemon trust, admission-not-revocation semantics and manual
cleanup after crashes remain as in ADRs 0032–0035. No paid provider, remote broker,
API/UI approval expansion or arbitrary host execution was introduced.

Stop for review. No commit or push.
