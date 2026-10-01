# Phase 6 acceptance and closure assessment

**Implementation and acceptance complete for the documented local scope; ready
for closure review.** Verified 2026-10-01 against source commit
`2ec2dc477a69fa7bae2947f6e686086fedb0ce5d`. Phase 7 has not started.

The charter requires a requested patch, a runtime pause, no write before approval,
approved continuation and rejection preventing action. The completed implementation
now demonstrates those gates through the real browser console, Next proxy, FastAPI,
PostgreSQL and fresh worker processes. No product functionality, tests, dependencies
or policy exceptions were added for closure. ADRs 0021–0025 remain authoritative.

## Charter-to-evidence audit

| Criterion                              | Observed evidence                                                                                                                                                                                                                                                                                       | Boundary                                                                                                 |
| -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| ApprovalRequest / agent requests patch | Two fresh `repository-patch-v1` workers read a public fixture and proposed the exact marker addition. Durable history contains model/tool outcomes and `approval.requested`; the browser displays approval ID, digest, full before/after and workspace fingerprints.                                    | Existing deterministic offline provider; no hosted-provider acceptance claim.                            |
| Runtime pauses                         | Both runs reached `WAITING_FOR_APPROVAL`, revision 2, pending approval, released worker lease and no apply intent. A fresh worker with `--allow-write` was not selected while waiting.                                                                                                                  | An execution grant does not substitute for approval.                                                     |
| No patch before required approval      | Both files matched proposal `before` while paused. After browser approval, the approved file still matched `before`, with no mutation intent until the separate worker invocation.                                                                                                                      | Approval does not dispatch work or itself write.                                                         |
| API and UI approval surface            | Actual browser input, exact-text disclosure, inspection acknowledgement, Approve/Reject button clicks and refresh used the production web build and real authenticated API. No direct HTTP decision or database decision edit was used.                                                                 | Local shared operator capability, not named reviewers or remote deployment.                              |
| Approval resumes execution             | Browser approval changed the run to `RUNNING`, revision 3; a fresh CLI worker with the separate write grant completed one successful apply intent. File bytes matched proposal `after`; refresh showed `SUCCEEDED` / `APPROVED`, revision 4, mutation `SUCCEEDED`. A duplicate worker was not selected. | Workspace checks, original deadline, explicit execution grant and single-use intent remain active.       |
| Rejection prevents action              | Browser rejection changed the second run to `FAILED` / `REJECTED`, revision 3. A fresh worker with a write grant was not selected; no apply intent existed and the file still matched `before`. Refresh retained the rejected outcome.                                                                  | FAILED alone is not generally proof of unchanged files; here both file and intent evidence were checked. |

The [database/file evidence](evidence/phase6/browser-acceptance.json) records both
run IDs, proposal text/digests, revisions, event ordering, original deadlines and
apply-call outcomes. The approved run contains one `approval.approved` event and
one succeeded apply call; the rejected run contains one `approval.rejected` event
and zero apply calls. Terminal jobs need not clear their old lease fields; terminal
selection exclusion was independently verified by fresh CLI invocations.

## Browser evidence

- [Approved, before worker](evidence/phase6/approved-before-worker.png): approval
  recorded, run RUNNING, no mutation intent.
- [Approved and applied](evidence/phase6/approved-applied.png): refreshed terminal
  success and successful mutation after the separately authorized worker.
- [Rejected, no mutation](evidence/phase6/rejected-no-mutation.png): refreshed
  rejection after a worker invocation was refused selection.

Both decision controls were disabled before inspection acknowledgement. Changing
the run ID removed the previous proposal and acknowledgement. The exact escaped
text disclosure was opened/read for both proposals. Terminal inspections offered
no repeat-decision controls. A syntactically valid but incorrect token was refused
without disclosing a proposal. Correcting it restored inspection. Forget cleared
the token/run/proposal, and reloading a successfully inspected page cleared them
again. These are real browser observations, supplementing the existing DOM tests.

Screenshots contain only public fixture data and password-masked credentials.
The generated credential was never printed or retained in the evidence. API/web
logs were checked for the token and then removed.

## Reproduce the operator flow

Use the [development](DEVELOPMENT.md), [patch worker](PATCHES.md) and
[console](APPROVAL_CONSOLE.md) instructions with a disposable migrated database,
two private ordinary-file checkouts and a fresh local operator token. Do not use a
shared or sensitive checkout.

1. For each checkout, invoke `runveil_worker.patch_worker submit`, then `work`
   without a write grant. Inspect the paused state and unchanged file.
2. Invoke `work --allow-write` while still paused: selection must be false.
3. Start Uvicorn and the production web build on loopback. Configure the web API
   origin; enter the token only in the console's password field.
4. Inspect the first run, expand exact text, acknowledge inspection and approve.
   Check the file is still unchanged before starting a fresh worker with
   `--allow-write`. Refresh and compare file bytes to the approved `after` text.
   A duplicate worker must not select the terminal run.
5. Inspect the second run, acknowledge inspection and reject. Invoke a fresh worker
   with `--allow-write`; it must not select the run. Verify no apply intent and
   unchanged file, then refresh the console.
6. Forget the token, close the browser tab, stop the servers and remove only the
   disposable acceptance database/checkouts/credential. Preserve sanitized evidence.

This execution used an external one-off coordinator for database creation,
subprocess setup, read-only evidence checks and cleanup. Browser decisions were
made through the UI using the computer-use tool. No new committed acceptance
framework or redundant test matrix was needed. See [handoff](PHASE_6F.md) for
verification commands, outcomes and environment details.

## Retained boundaries and closure

Existing tests cover races/stale revisions, profile separation, provenance,
transaction rollback, separate write permission, original budgets, workspace drift,
preimage/filesystem validation and uncertain mutation intent without replay.
The browser demonstration closes the remaining UI integration evidence gap; it does
not replace those deterministic tests or claim browser fault injection coverage.

The accepted implementation remains one ordinary top-level file in an exclusively
assigned trusted local checkout. Shared-token authentication provides no named
human attribution, per-run ACL or tenant isolation. Browser extensions/password
managers and hostile same-origin scripts are outside the memory-only guarantee.
No sandbox, arbitrary commands, multi-file patches, live hosted/SQS approval flow,
remote deployment, atomic database/filesystem commit or exactly-once side effects
are claimed. Uncertain mutations remain terminal without automatic replay.

No required Phase 6 charter acceptance item remains open within these boundaries.
Review closure, then authorize a focused Phase 7 slice separately. No automatic
continuation, commit or push is authorized.
