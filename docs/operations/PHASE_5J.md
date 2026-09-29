# Phase 5J handoff — admission quarantine and verified release

Implemented 2026-09-29; stopped for review. No commit or push.

## Scope and decisions

Started from a clean repository. Inspected AGENTS.md, the charter, architecture,
roadmap, accepted worker/repository/broker decisions and the completed claim,
execution-store, outbox and worker implementation. The current request authorizes
continuation beyond Phase 5I's review gate. Selected the planned quarantine/repair
slice, restricted to explicit configuration rejections in `fixture-calls-v1`.

Execution-store start now distinguishes `ConfigurationRejected` (a ValueError
subtype) from unrelated exceptions. The calls-profile worker records that rejection
under its live claim and re-raises it. Migration 0008 adds admission count/revision,
cooldown and quarantine state plus a separate append-only audit table. Recording
clears ownership, imposes a 30-second cooldown and quarantines on the third durable
rejection. Polling and outbox selection exclude blocked jobs. Existing broker
messages remain unacknowledged under the terminal-only rule.

Operator inspection exposes bounded metadata. Explicit release requires the
observed admission revision, quarantine, a nonterminal run, no live owner and the
same supported immutable configuration. It resets admission state and appends audit
atomically. It never edits configuration, checkpoints, invocation records, retry
schedules or original deadlines. Invalid pinned versions require replacement
versions/runs and cancellation, not in-place repair. Runtime history remains
unchanged, including its recovery event watermark. No new dependencies or core
runtime schema were introduced.

The classification intentionally excludes provider/tool errors, DB/ownership failures,
cancellation, checkpoint/history corruption, malformed broker messages, repository
capture and other profiles. This closes the concrete repeated-configuration-rejection
path without turning arbitrary failures or uncertain execution into retries.
See [ADR 0020](../adr/0020-worker-admission-quarantine.md) and
[admission operations](ADMISSION.md).

Also corrected an outdated architecture sentence that still described broker
integration as future work despite the completed Phase 5I adapter.

## Files

Created:

- `apps/worker/src/runveil_worker/admission.py`: local inspection and release CLI.
- `packages/persistence/src/runveil_persistence/admission.py`: claim-fenced rejection
  recording, inspection, revision/binding-checked release and audit.
- `packages/persistence/migrations/versions/0008_admission_quarantine.py`: job state,
  constraints and append-only audit migration.
- `packages/persistence/tests/test_admission.py`: five focused behavioral cases.
- `docs/adr/0020-worker-admission-quarantine.md`, `docs/operations/ADMISSION.md`, this handoff.

Modified:

- `apps/worker/src/runveil_worker/worker.py`: narrow calls-profile rejection handling.
- `packages/persistence/src/runveil_persistence/execution.py`: typed start rejection.
- `packages/persistence/src/runveil_persistence/jobs.py`, `outbox.py`: admission
  selection checks and execution fence quarantine check.
- `packages/persistence/src/runveil_persistence/models.py`: admission mappings.
- `packages/persistence/tests/test_persistence.py`: table inventory and populated
  migration defaults; `test_broker.py`: legacy seed uses the actual pre-0008 schema.
- `README.md`, `ARCHITECTURE.md`, `ROADMAP.md`, `docs/operations/WORKER.md`,
  `docs/operations/BROKER.md`, `docs/operations/PERSISTENCE.md`: current boundaries.

## Verification

Python 3.12, uv 0.12.19, Node 24.19.0; disposable PostgreSQL 17.9, Compose project
`runveil-phase5j`, port 55435. Public synthetic fixtures only; no live AWS/model
calls or paid acceptance check. SDK tests use explicit offline credentials.

- `uv sync --locked --all-packages`, `npm ci` — passed; manifests/locks unchanged.
  npm reported zero vulnerabilities and existing ESLint deprecation/optional
  install-script notices; no approval settings changed.
- `uv run ruff format --check .`, `uv run ruff check .`, `uv run mypy` — passed;
  73 strictly checked source files.
- Focused admission/broker/persistence suite — **19 passed**. New cases verify
  three-rejection quarantine/cooldown, polling/publication suppression, unacknowledged
  quarantined delivery, unchanged runtime history/no dispatch, restored binding
  release, concurrent revision conflict, invalid immutable pin refusal, cancelled
  release refusal, stale/duplicate reports, rollback, immutable audit, original
  deadline preservation and uncertain-intent failure without replay. An ordinary
  unclassified start ValueError does not increment admission count or release ownership.
- `RUNVEIL_TEST_DATABASE_URL=…/postgres uv run pytest -q` — **257 passed**, including
  **126 PostgreSQL integration cases**. Existing recovery, broker, repository,
  cancellation and budget behavior also passed.
- `DATABASE_URL=…/runveil uv run alembic upgrade head`, `uv run alembic check` —
  passed through 0008; no metadata drift. Integration coverage includes populated
  upgrades, constraint names/defaults and full downgrade/re-upgrade.
- `npm run format:check`, `npm run lint`, `npm run typecheck`, `npm test`,
  `npm run build` — passed; one web test.
- `uv run python scripts/smoke.py` with database configured and with `DATABASE_URL`
  unset — API/web health, production home page and readiness contracts passed.
- Separate CLI processes inspected a prepared quarantined public fixture, rejected
  a stale release revision with fixed `admission_failed`/exit 1, released revision 3
  to revision 4 with zero failures, then completed normal polling execution:
  `SUCCEEDED steps=3 retries=0`. Missing release revision rejected with exit 2.
  Inspection output contained no task or ownership token. The disposable fixture
  preparation advanced cooldown timestamps instead of waiting between failures.
- `git diff --check` — passed.

Zero test databases remained. The disposable Compose service and volume were
removed after verification. Other services and local environment files were untouched.

## Remaining concerns and next slice

Only committed configuration rejections for the calls profile count. A crash before
recording can leave the lease until expiry and needs another admission attempt.
Quarantine/cooldown may delay expired-budget finalization until verified release;
the deadline is never extended. Already-published or concurrently sent broker
notifications remain possible, but current claims refuse quarantined execution.
Malformed messages and unclassified failures still require operator investigation.

Stop older workers/relays before relying on the new policy; mixed-version rolling
operation is not supported. Operators/database owners remain trusted; this is not
an authenticated administration service. Audit can grow across explicit release
cycles and has no cleanup. Downgrade removes admission controls/audit and may make
blocked work eligible; it is not a repair mechanism. Live AWS/IAM/redrive acceptance
remains unverified and separately opt-in.

Review Phase 5J, then consolidate Phase 5 acceptance with a focused reproducible
process-crash/restart and duplicate-delivery demonstration using existing public
profiles, and map charter reliability criteria to evidence and explicit gaps.
Prefer that acceptance slice over another independent feature; decide Phase 5
closure/Phase 6 entry at review. Hosted retry safety, mutations, approvals and MCP
remain outside the current evidence. No declaration of Phase 5 completion is made.
