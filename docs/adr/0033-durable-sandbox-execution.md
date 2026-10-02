# ADR 0033: Pinned durable sandbox test execution

- Status: Accepted for Phase 10B
- Date: 2026-10-02

## Decision

Add `sandbox-tests-v1`, an offline worker profile for one `tests.run` call against
`clamp-v1`. Configuration/checkpoint version 12 pins the reviewed immutable image,
fixture/policy version, local socket identity and covered implementation digest.
It uses all existing elapsed/token/cost/step/invocation budgets and no retries.
Versions 9–11 keep their repository bindings and review/write semantics; version
12 has a sandbox binding instead of a repository workspace or approval state.

Keep the general registry read-only. A narrow core-owned execution branch advertises
and dispatches only `tests.run`, with empty arguments and both pinned and operator
EXECUTE grants. The worker requires explicit `--allow-execute`. No command, image,
fixture, path or environment can be supplied by a model. No WRITE or NETWORK grant,
approval substitution, host checkout, patching or persistent workspace is added.

Use existing model/tool intents, checkpoints, fences and telemetry. Commit intent
before Docker I/O; derive the container name from its durable tool-call UUID. Recheck
ownership, revision, history and deadline before create and before start; perform
Docker I/O outside database transactions. Completion rechecks the same fences and
rejects late outcomes. These checks cannot atomically revoke a Docker request after
it is sent or a process paused immediately after admission. This preserves the
existing external-call fencing guarantee, not exactly-once execution or OS revocation.
The supported image watchdog and disposable/no-network boundary remain in force.

Return a bounded typed test observation and then a scripted final summary. A failed
test suite is a successful observation with `tests_failed`, not a runtime failure
or a solved task. Infrastructure and uncertain-cleanup errors fail the tool. Output
is untrusted, capped at 4096 characters with explicit truncation. Full container
output is not copied into telemetry. Runtime trace projections continue to omit
raw tool payloads; durable tool records/context retain the bounded observation.

## Recovery and limits

Clean model/tool checkpoints resume without repeating committed outcomes. An
unresolved model/tool intent terminates with existing `execution_interrupted`
semantics, without constructing a sandbox adapter, accessing Docker or replaying
execution. This terminal-only route works without an image/socket/EXECUTE grant.
It verifies the enrolled profile and complete fixed configuration before start.
A completed run is not selected again. No schema migration or new dependency.

The container name `runveil-sandbox-<tool-call UUID hex>` remains derivable even
when no outcome committed. Recovery does not automatically remove uncertain
containers: daemon create requests can finish late, and cleanup is not a durable
revocation fence. Operators inspect that exact name after a crash or a
`sandbox_cleanup_unconfirmed` error. A budget/ownership failure may take precedence
over a cleanup error; only a committed `cleanup_confirmed` result proves observed
removal. No cleanup reconciler, hostile-image sandbox,
remote Docker, real provider or multi-task coding claim is made.

This explicitly advances ADR 0032's operator-only boundary with the narrow durable
profile above; its existing standalone CLI and isolation limits remain supported.
