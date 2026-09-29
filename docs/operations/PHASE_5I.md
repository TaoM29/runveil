# Phase 5I handoff — SQS notification outbox

Implemented 2026-09-29; stopped for review. No commit or push.

## Scope and decisions

Started from a clean repository. Inspected AGENTS.md, the charter, architecture,
roadmap, accepted worker/repository decisions, Phase 5H evidence and the completed
worker/claim/store/repository implementation. The current request authorizes the
next slice beyond the prior review gate. Selected the planned broker/database
consistency boundary, restricted to the public `fixture-calls-v1` profile.

Migration 0007 introduces one opt-in outbox row per job, created atomically with
run/version/job and an immutable queue destination. Existing jobs are not adopted.
The separately leased relay sends outside transactions and fences completion.
Successful sends postpone the next notification by 30 seconds; failed/uncertain
sends leave a 60-second publication lease to expire. Repeated eligibility scanning
recovers lost messages and expired execution leases without treating publication
as execution ownership or adding hooks to every runtime transition.

The boto3 SQS Standard adapter accepts only version/run-ID envelopes. Consumers
check the destination and fixed profile in PostgreSQL, then use existing claims.
Only committed terminal state permits deletion. Early/busy/invalid messages and
exceptions remain unacknowledged. SDK operations are bounded, with one attempt;
CLI commands are explicit one-shot submit/publish/work entry points. Existing
polling remains available. No new core abstraction, runtime schema, hosted call,
repository consumer or AWS infrastructure was introduced.

The recurring outbox intentionally trades extra notifications for a simple durable
recovery path. It is not a throughput-optimized production scheduler. See
[ADR 0019](../adr/0019-sqs-notification-outbox.md) and [broker operations](BROKER.md).

## Files

Created:

- `apps/worker/src/runveil_worker/sqs.py`: bounded SDK adapter, strict envelope,
  fixed-profile relay/consumer and opt-in CLI.
- `packages/persistence/src/runveil_persistence/outbox.py`: enrollment, separately
  fenced publication claims/completion and destination/profile membership lookup.
- `packages/persistence/migrations/versions/0007_notification_outbox.py`: outbox,
  due index, lease constraints and immutable destination guard.
- `packages/persistence/tests/test_broker.py`: four focused behavioral integration
  tests combining real PostgreSQL with offline SDK wire stubs.
- `docs/adr/0019-sqs-notification-outbox.md`, `docs/operations/BROKER.md`, this handoff.

Modified:

- `apps/worker/src/runveil_worker/worker.py`: optional atomic outbox enrollment
  limited to the calls fixture profile.
- `packages/persistence/src/runveil_persistence/models.py`: outbox mapping.
- `packages/persistence/tests/test_persistence.py`: migration table inventory.
- `apps/worker/pyproject.toml`, `pyproject.toml`, `uv.lock`: boto3 and development
  SDK typing dependencies; no manual AWS signing/HTTP implementation.
- `README.md`, `ARCHITECTURE.md`, `ROADMAP.md`, `docs/operations/PERSISTENCE.md`,
  `docs/operations/WORKER.md`: current scope, transport and migration boundaries.

## Verification

Python 3.12, uv 0.12.19, Node 24.19.0; disposable PostgreSQL 17.9, Compose project
`runveil-phase5i`, port 55435. No live AWS or paid model calls. SDK stubs use explicit
non-secret offline credentials; live credentials were not needed.

- `uv lock`, `uv sync --locked --all-packages`, `npm ci` — passed. boto3 locked to
  1.43.104 with matching service typing. npm reported zero vulnerabilities and
  existing ESLint deprecation/optional install-script notices; settings unchanged.
- `uv run ruff format --check .`, `uv run ruff check .`, `uv run mypy` — passed;
  69 strictly checked source files.
- Focused broker suite — four passed. It covers populated 0006 upgrade/no backfill,
  downgrade/re-upgrade preservation of runs, transaction rollback, idempotent
  enrollment/destination guards, unknown sends, crash after accepted send,
  competing relay claims, stale/expired completion refusal, periodic republish,
  active/expired execution leases, terminal suppression, committed success before
  failed delete, duplicate acknowledgement without extra invocations, early/busy
  messages, malformed/oversized/version-invalid bodies, unknown/other-destination/
  unenrolled runs and unsafe queue URLs.
- `RUNVEIL_TEST_DATABASE_URL=…/postgres uv run pytest -q` — **252 passed**, including
  **121 PostgreSQL integration cases**. Existing worker recovery, cancellation,
  uncertain-intent, repository identity and budget cases passed unchanged.
- `DATABASE_URL=…/runveil uv run alembic upgrade head`, `uv run alembic check` —
  passed through 0007; no metadata drift. Full migration round-trip and guard checks
  are included in the suite.
- `npm run format:check`, `npm run lint`, `npm run typecheck`, `npm test`,
  `npm run build` — passed; one web test.
- `uv run python scripts/smoke.py` with database configured and with `DATABASE_URL`
  unset — API/web health, production home page and readiness contracts passed.
- Separate CLI processes used `runveil_worker.sqs submit --queue-url` (database
  only) and the polling fallback with the returned run ID: `SUCCEEDED steps=3
retries=0`. Persisted outbox destination and terminal checkpoint verified.
  An invalid queue URL failed parsing with exit 2 and no traceback. Publication,
  receive and delete calls were verified through SDK stubs, not live CLI AWS calls.
- `git diff --check` — passed.

Zero test databases remained. The disposable Compose service and volume were
removed after verification. Other services and local environment files were untouched.

## Remaining concerns and next slice

Live AWS delivery, credentials, IAM/redrive configuration and deployment acceptance
remain unverified and explicitly opt-in. Only commercial regional SQS Standard
URLs and the fixed public fixture profile are supported. Queue visibility does
not replace the 660-second execution lease or guarantee exactly-once execution.
Cooperative cancellation cannot undo a running SDK call.

The relay must be invoked repeatedly; there is no supervisor/heartbeat, outbox
cleanup, metrics or broker readiness endpoint. Repeated notifications incur extra
messages/cost. Poison messages stay unacknowledged, and corrupt enrolled jobs can
continue producing hints; no automatic quarantine/repair policy is claimed.
Downgrade to 0006 deletes outbox enrollment/publication state and re-upgrade does
not restore it, although runs/jobs/history and polling remain intact.

Review Phase 5I, then implement a bounded quarantine and operator repair policy
for repeated failures before execution, preserving ownership/history and never
replaying uncertain execution. Live AWS acceptance is a separate opt-in check;
provisioning remains Phase 12. Hosted retry policy, approvals, mutations and MCP
remain outside this slice. Phase 5 is not declared complete.
