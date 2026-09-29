# Phase 5 acceptance and closure assessment

**Implementation and acceptance complete for the documented scope; ready for
closure review.** Verified 2026-09-29. Phase 6 has not started.

The charter's Phase 5 gate requires worker crash → restart → checkpoint recovery
→ successful continuation, plus duplicate-message safety. The process demonstration
below now proves that sequence with actual SIGKILL and fresh interpreter processes.
The existing integration suite covers the remaining reliability boundaries. No
additional production behavior was needed for acceptance.

This closes the engineering work for Phase 5 under accepted ADRs 0011–0020. It does
not declare a production deployment, live SQS acceptance, hosted retry safety or
exactly-once external effects. Those claims were not part of the charter's Phase 5
acceptance gate; live infrastructure remains Phase 12. No required acceptance item
is left open within the supported fixed profiles and documented boundaries.

## Charter-to-evidence audit

| Phase 5 criterion                          | Implemented behavior and evidence                                                                                                                                                                                                                                                                                                                                                                                                    | Boundary                                                                                                                  |
| ------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------- |
| Background worker outside API lifecycle    | `runveil_worker` process owns polling/execution; the acceptance command restarts workers in fresh processes. [Worker tests](../../packages/persistence/tests/test_worker.py) cover ownership and recovery.                                                                                                                                                                                                                           | No HTTP execution endpoint or production supervisor.                                                                      |
| Queue abstraction and SQS target           | PostgreSQL selection/outbox and the `SqsQueue` adapter separate notifications from execution claims. [Broker tests](../../packages/persistence/tests/test_broker.py) verify SDK wire calls, enrollment rollback, relay fencing and send/delete uncertainty. The process demo runs real consumer logic with SDK stubs.                                                                                                                | SQS Standard adapter is offline verified for `fixture-calls-v1`; no new unused generic queue framework or live AWS claim. |
| Idempotency and duplicate-message safety   | Per-run leased claims and immutable outcomes prevent repeated committed work. Process demo redelivers identical run notifications before recovery and after terminal commit; persisted history stays unchanged on terminal redelivery.                                                                                                                                                                                               | Independent submissions create independent runs. External effects are not exactly once.                                   |
| Retry policy                               | Pinned count, explicit safe retry grant and failed-attempt provenance; [retry tests](../../packages/persistence/tests/test_retries.py) cover permitted and refused retry paths and restart boundaries.                                                                                                                                                                                                                               | Known safe scripted rate-limit failures only in exposed worker profiles; no blanket hosted/tool retries.                  |
| Backoff                                    | Persisted database-clock eligibility and bounded exponential delay, with recovery and cancellation checks in the same retry tests.                                                                                                                                                                                                                                                                                                   | No jitter/general scheduling framework.                                                                                   |
| Cancellation                               | [Execution tests](../../packages/persistence/tests/test_execution.py) reject late outcomes after cancellation; retry tests cover cancellation during backoff. Terminal cancellation prevents future claims.                                                                                                                                                                                                                          | Cannot undo an already dispatched external request; cooperative cancellation is not a hard sandbox.                       |
| Durable resume and successful continuation | Actual SIGKILL after a committed tool result; fresh consumer completes with the original tool ID/result, three total steps and preserved accounting/deadline. [Worker tests](../../packages/persistence/tests/test_worker.py) cover additional commit boundaries.                                                                                                                                                                    | Clean checkpoints resume. Uncertain intent fails without replay; the second process scenario verifies this explicitly.    |
| Budget system                              | [Elapsed](../../packages/persistence/tests/test_elapsed_budget.py), [token](../../packages/persistence/tests/test_token_budget.py), [cost](../../packages/persistence/tests/test_cost_budget.py), [call-limit](../../packages/persistence/tests/test_call_limits.py) and [execution](../../packages/persistence/tests/test_execution.py) tests cover persisted bounds, rollback, stale owners, unknown usage and exact-limit finish. | Cooperative time limits and reported-usage stop thresholds, not hard real-time or billing guarantees.                     |
| Loop limits                                | [Repeated-tool tests](../../packages/persistence/tests/test_repeated_tools.py) verify canonical call identity across recovery, failures and retries; total-step and independent invocation caps remain active.                                                                                                                                                                                                                       | No semantic loop inference.                                                                                               |

Additional Phase 5 boundaries are also verified: [repository recovery](../../packages/persistence/tests/test_repository_worker.py)
refuses workspace/content/implementation drift; [admission tests](../../packages/persistence/tests/test_admission.py)
verify cooldown, three-rejection quarantine, immutable audit, verified operator
release and preservation of uncertain intent/deadlines. These are supporting
boundaries, not reasons to expand the completion slice into new features.

## Reproduce the process demonstration

Use the README's locked dependency and local PostgreSQL setup. The admin role must
have CREATEDB. From the repository root, on POSIX (Linux/macOS):

```sh
export RUNVEIL_TEST_DATABASE_URL='postgresql+psycopg://runveil:runveil-local-only@127.0.0.1:5432/postgres'
uv run python scripts/phase5_acceptance.py
```

The command creates/migrates a randomly named `runveil_acceptance_*` database and
drops that database on completion/failure. It never resets the database named by
the admin URL and does not use the caller's `DATABASE_URL` for acceptance work.
Do not disable Python assertions (`-O`); the command refuses optimized execution.
The internal child arguments are harness plumbing, not an operator worker interface.

Two public `fixture-calls-v1` runs exercise these paths:

1. Publish an offline SQS notification, then run a child using the existing core,
   profile and persistence store. A script-local store wrapper pauses immediately
   after the tool outcome/checkpoint commits. The parent sends SIGKILL and verifies
   the child's signal exit. No graceful cleanup simulates the crash.
2. A fresh consumer process receives the same notification and defers while the
   original execution lease is live. Runtime history is unchanged.
3. After confirmed child death, the harness advances **only that job's lease expiry
   in its own disposable database**. This avoids waiting the production 660-second
   lease; it does not change lease constants, checkpoints, deadlines or code policy.
4. A fresh consumer completes the run. Assertions check the same committed tool
   identity/result, two total model calls/one tool call, three steps, 20 input/10
   output synthetic tokens, 50,000 nano-USD and the original deadline.
5. Another fresh consumer receives the duplicate and acknowledges terminal state
   without changing the checkpoint or history.
6. Repeat at the tool-request-intent boundary. Recovery must produce FAILED with
   `execution_interrupted`, two consumed steps and the original single failed tool
   record; no second model call or tool replay is permitted. Terminal duplicate
   acknowledgement again leaves history unchanged.

Expected output:

```text
PASS checkpoint: SIGKILL -> SUCCEEDED steps=3 error=None; active-lease deferral and duplicate acknowledgement
PASS intent: SIGKILL -> FAILED steps=2 error=execution_interrupted; active-lease deferral and duplicate acknowledgement
PASS disposable database removed; no live AWS/provider calls
```

SDK stubs intercept send/receive/delete in every process, using explicit offline
credentials. They validate the expected wire parameters and current receipt handle;
no emulator or actual queue is involved. Fixed output excludes raw errors, tasks,
credentials, ownership tokens and DB URLs. Child waits are bounded and child
processes are reaped. As with other disposable test tools, forcibly killing the
parent or losing PostgreSQL can prevent cleanup; any remaining acceptance database
must be inspected and removed explicitly, never by resetting the admin database.

CI runs this command after the existing pytest suite. It complements the deterministic
boundary tests rather than adding a second matrix of equivalent pytest cases.

## Closure limits and next phase

The intentional lease-time shortcut proves expiry admission logic, not 660 seconds
of wall-clock waiting. Commit-barrier SIGKILL tests precise crash locations rather
than arbitrary machine/power failure. The existing transaction/ownership tests cover
rollback and competing owners. Neither the harness nor SDK stubs verify actual AWS
network delivery, IAM, queue redrive/retention configuration or deployment behavior.

Other limits remain: fixed supported profiles; snapshot recovery needs the same
selected local bytes/root; no hosted retry/idempotency policy; admission quarantine
covers only explicit calls-profile configuration rejections; no broker supervisor,
metrics, audit/outbox retention or general malformed-message quarantine. Budget
and external-effect limits remain as documented in the accepted ADRs. None is
silently promoted to a production guarantee by this acceptance result.

Review Phase 5 closure, then begin a separately authorized Phase 6A: the durable
approval-request and pause/resume boundary for one controlled patch proposal.
No patch may be applied before required approval; rejection must prevent action.
Keep filesystem mutation gated until that boundary is implemented and reviewed.
The original charter is preserved; this assessment records evidence and scope,
not a rewrite of its goals. Full commands/results and changed files are in the
[Phase 5K handoff](PHASE_5K.md).
