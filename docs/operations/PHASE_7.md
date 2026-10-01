# Phase 7 acceptance and closure assessment

**Implementation and acceptance complete for the documented local scope; ready
for closure review.** Verified 2026-10-01 against source commit
`584eae69aeb90cf0d9f6bbbbdf2affe9c1bcf0c4`. Phase 8 has not started.

The charter requires understandable execution: model/tool calls, durations, errors,
retries, tokens, estimated cost, approval state and final result, agreeing with
persisted events. ADRs 0026–0028 implement this through the authenticated durable
trace API, local read-only console, and opt-in OTel/structured JSON telemetry.
Fresh execution, actual HTTP requests, database comparisons and real browser
inspection now demonstrate these components together. No application code, tests,
dependencies, schemas or authorization behavior changed for closure.

## Charter-to-evidence audit

| Criterion                           | Evidence                                                                                                                                                                                                                                          | Meaning and boundary                                                                                                                                    |
| ----------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Model/tool calls                    | Fresh completed run: 2 model/1 tool intents; failed run: 3/2; retried run: 4/1; approval wait: 2/2. API event annotations and browser counts match raw invocation rows.                                                                           | Counts are committed intents, including unresolved calls; no invented dispatch for work that did not run.                                               |
| Durations                           | Every projected call duration equals database completion minus request time. Browser renders those intervals and overall elapsed time; JSON spans have ordered local timestamps.                                                                  | Persisted wall time and locally observed dispatch time are different measures. Approval waits and retry downtime are included in run elapsed time.      |
| Errors                              | Loop fixture terminates with `repeated_tool_limit_exceeded`; the browser shows the error and retained accounting. Retried model calls show `provider_rate_limited`.                                                                               | Raw exception text and stack traces are omitted; a failed run can contain successfully completed calls.                                                 |
| Retries                             | Cost fixture succeeds after two scheduled retries across three fresh workers. Two API retry links identify failed model predecessors. OTel roots are `retry_wait`, `retry_wait`, `succeeded`, with distinct trace IDs and one durable run ID.     | Cumulative root accounting must not be summed across resumes.                                                                                           |
| Tokens and cost                     | Completed/retried/paused runs show 20 input, 10 output tokens and USD 0.000050000. Failed run retains 30/15 and USD 0.000075000. Latest checkpoint, API and last root agree.                                                                      | Pinned-price estimates, not invoices. Existing tests cover unknown components/subtotals; Phase 7B browser evidence covers unavailable older accounting. |
| Approval state                      | Patch worker pauses at `WAITING_FOR_APPROVAL` / `PENDING`; the browser shows the same approval ID. Reads and refused decisions leave revision, events, approval and file unchanged; no apply intent exists.                                       | Descriptive state grants no decision or WRITE authority. A separately granted worker is not selected while waiting.                                     |
| Final result                        | Completed and retried views show the persisted fixture summary; failed and paused views show no final summary.                                                                                                                                    | Operator-visible bounded text, not arbitrary artifacts or a general redaction guarantee.                                                                |
| Trace API/UI                        | Production Next.js console reads the real FastAPI service and PostgreSQL. All four views inspected in the actual browser. Seven five-event HTTP proxy pages reconstruct the retried run's 35 ordered events exactly.                              | Existing 7B browser evidence already covers the UI's 50-event continuation through 113 events. No mock browser responses.                               |
| OTel/structured output              | Fresh CLI stderr contains 23 bounded JSON records: 6 execute roots and 17 model/tool children. Every child ID/request sequence resolves to the raw durable invocation; root accounting matches the checkpoint.                                    | Best effort, disabled by default. Durable traces remain authoritative, including when spans are lost or root completion precedes worker finalization.   |
| Authentication/read-only boundaries | Missing/wrong/approval credentials cannot read traces (401); trace credential cannot inspect or decide approvals (401). Auth precedes malformed-ID parsing. Trace proxy POST returns 405; stale watermark returns 409; unknown query returns 422. | Independent shared local capabilities, not named identities, per-run ACLs or public deployment security.                                                |

The [sanitized evidence](evidence/phase7/closure-acceptance.json) retains four API
snapshots, emitted JSON spans, correlation assertions, boundary response codes and
browser observations. The coordinator compared API results directly with run,
event, checkpoint and invocation rows, rather than comparing two uses of the same
projection helper. The retried trace's complete event list was also reconstructed
through the actual authenticated web proxy. A final database check after browser
inspection confirmed all four statuses, revisions and event watermarks unchanged.

## Browser evidence and credentials

- [Completed](evidence/phase7/closure-completed.png): success, accounting and final summary.
- [Failed](evidence/phase7/closure-failed.png): retained accounting and loop-limit error.
- [Retried](evidence/phase7/closure-retried.png): four model attempts, two retries and final success.
- [Approval wait](evidence/phase7/closure-approval-wait.png): pending review without execution authority.

Actual browser interaction also verified a refused token exposes no trace, a
corrected token restores inspection, call correlation expands to the durable
invocation ID/request/outcome positions, and editing the run selects fresh evidence.
Forget and reload clear both fields and evidence. Navigation to approvals requires
blank separate fields; browser Back returns to a blank trace form. No browser
approval decision was attempted in this audit; the trace-token decision rejection
was checked through HTTP, with the separate approval capability independently valid.

Fresh random tokens stayed in process memory and a private temporary file used to
fill the password field; neither was printed or retained in evidence. Screenshots
contain public fixture data. API/web logs were checked for both credentials. The
browser tab, services, temporary coordinator/credentials/checkout and task-owned
Compose volume were removed after verification.

## Reproduce the focused acceptance

Use [development](DEVELOPMENT.md), [trace operations](TRACES.md) and
[telemetry operations](TELEMETRY.md) with an isolated migrated database and distinct
generated trace/approval tokens. Configure only the API with those tokens; the web
server receives its fixed loopback API origin, not a server-owned credential.

1. With `RUNVEIL_TELEMETRY=json`, submit/work `fixture-calls-v1` and
   `fixture-loop-v1` in fresh worker processes. The loop worker exits 1 as expected.
2. Submit `fixture-cost-v1`; run three `work --once` invocations, respecting the
   first one-second and second two-second retry delays. Preserve each stderr batch.
3. Submit/work `repository-patch-v1` using the existing patch-worker CLI and one
   public ordinary-file checkout. Preserve the pending approval; do not decide it.
4. Read each `/runs/{id}/trace` with the trace bearer. Compare status/revision,
   ordered events, invocation identities/outcomes/timestamps, checkpoint accounting
   and final summary with raw database rows. Match span invocation IDs/request
   sequences, parent IDs, root outcomes and cumulative accounting.
5. Start the production web build. Inspect all four runs in `/traces`, expand call
   correlation, check error/retry/approval distinctions, then test Forget/reload and
   separate approval-page navigation. Exercise bounded proxy pagination and refused
   credentials/methods/watermarks via HTTP. Recheck the pending file and database.
6. Retain only sanitized evidence; remove the disposable setup. Full commands and
   regression results are in the [Phase 7D handoff](PHASE_7D.md).

## Closure and retained limits

No required Phase 7 charter acceptance item remains open within ADRs 0026–0028's
local scope. Acceptance is based on this integrated evidence plus existing
focused boundary tests and earlier browser evidence, not new product features or
an exhaustive test matrix. The original charter remains unchanged.

Per-attempt token/provider-latency UI projection, metrics, collector delivery,
cross-process trace propagation, public demos/deployment, run discovery and
multi-tenant access remain outside this accepted slice. The charter's durations,
usage and cost gates are met by clearly labelled persisted intervals and checkpoint
accounting; pure provider latency and detailed per-attempt usage are not implied.

The API omits content-bearing payloads but selected labels/final summaries are
operator data. Memory-only credentials do not defend against extensions or hostile
same-origin scripts. Active history can invalidate pagination. OTel may drop records
on saturation, output failure or abrupt death; root completion does not prove worker
finalization. A stalled output sink can delay CLI shutdown by the SDK join (up to
30 seconds). Telemetry never authorizes retries, writes or reconstruction of missing
history. No hosted provider, AWS, collector or cross-browser certification is claimed.

Review Phase 7 closure, then separately authorize a focused Phase 8 evaluation
slice. There is no automatic continuation, commit or push.
