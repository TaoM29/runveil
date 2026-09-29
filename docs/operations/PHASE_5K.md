# Phase 5K handoff — completion and acceptance

Verified 2026-09-29. **Phase 5 implementation and acceptance are complete within
the documented scope, ready for closure review.** Phase 6 is not started.
No commit or push.

## Scope and findings

Started from a clean repository and inspected AGENTS.md, charter Phase 5 criteria,
architecture, roadmap, accepted reliability ADRs, Phase 5J evidence and the completed
worker/store/claim/outbox/consumer/admission implementation and tests. The user
explicitly requested acceptance and closure if possible.

The existing suite already covered deterministic ownership, crash-boundary restore,
retry/backoff, cancellation, budgets, repository identity, broker consistency and
quarantine behavior. The remaining acceptance evidence gap was actual process death
and subsequent fresh-process delivery. Added one script, not new production behavior
or a parallel matrix of pytest cases. No migration, dependency, manifest, lockfile
or runtime policy changes were needed; no new architecture ADR is warranted because
this consolidates existing accepted decisions.

The harness creates its own disposable PostgreSQL database and public fixture runs.
It verifies actual SIGKILL at a committed tool checkpoint and at tool intent, live-
lease deferral, fresh-process consumer recovery, preserved deadline/accounting,
terminal acknowledgement and duplicate history stability. Checkpoint recovery
succeeds; uncertain intent fails conservatively without replay. All SQS calls use
SDK stubs; no AWS or provider call is made. CI runs the script after pytest.

The [acceptance audit](PHASE_5.md) maps each charter criterion to implementation
and verifiable evidence. No required criterion remains open in the accepted scope.
Live AWS/IAM acceptance, hosted retry safety and production guarantees are explicitly
not inferred from offline verification. The charter does not require those claims
for its Phase 5 crash/restart/recovery and duplicate-delivery gate. Review closure,
then authorize Phase 6 separately.

## Files

Created:

- `scripts/phase5_acceptance.py`: two bounded process-death scenarios, offline SDK
  wire validation, persisted evidence checks and owned database/process cleanup.
- `docs/operations/PHASE_5.md`: acceptance matrix, reproduction, scope and closure assessment.
- `docs/operations/PHASE_5K.md`: this verification/handoff record.

Modified:

- `.github/workflows/ci.yml`: run process-death acceptance after pytest.
- `README.md`, `CONTRIBUTING.md`: current completion status and acceptance command/setup.
- `ROADMAP.md`, `ARCHITECTURE.md`: Phase 5 acceptance/closure and Phase 6 review boundary.
- `docs/operations/WORKER.md`, `docs/operations/BROKER.md`: link the executable evidence
  and distinguish offline verification from live AWS acceptance.

Production source and existing tests are unchanged.

## Verification

Python 3.12, uv 0.12.19, Node 24.19.0; disposable PostgreSQL 17.9, Compose project
`runveil-phase5k`, port 55435. Commands ran locally, not on a hosted CI runner.
The CI definition now includes the same acceptance command.

- `uv sync --locked --all-packages`, `npm ci` — passed; manifests/locks unchanged.
  npm reported zero vulnerabilities plus existing ESLint deprecation/optional
  install-script notices; no approval settings changed.
- `uv run ruff format --check .`, `uv run ruff check .`, `uv run mypy` — passed;
  74 strictly checked source files.
- `RUNVEIL_TEST_DATABASE_URL=…/postgres uv run pytest -q` — **257 passed**, including
  **126 PostgreSQL integration cases**. Test count unchanged from Phase 5J.
- `RUNVEIL_TEST_DATABASE_URL=…/postgres uv run python scripts/phase5_acceptance.py` —
  passed after implementation, then again with final output and the full suite:

```text
PASS checkpoint: SIGKILL -> SUCCEEDED steps=3 error=None; active-lease deferral and duplicate acknowledgement
PASS intent: SIGKILL -> FAILED steps=2 error=execution_interrupted; active-lease deferral and duplicate acknowledgement
PASS disposable database removed; no live AWS/provider calls
```

- The process demo asserts original tool identity/result, invocation counts,
  unchanged pre-recovery/terminal event histories, original deadline and successful
  run totals of 20 input/10 output tokens and 50,000 synthetic nano-USD. The uncertain
  run retains one model/one failed tool record without new execution.
- Explicit command checks with no test admin URL and with optimized Python (`-O`)
  refused execution with exit 1 and fixed failure output, without a traceback.
- `DATABASE_URL=…/runveil uv run alembic upgrade head`, `uv run alembic check` —
  passed through existing 0008; no metadata drift or new migrations.
- `npm run format:check`, `npm run lint`, `npm run typecheck`, `npm test`,
  `npm run build` — passed; one web test.
- `uv run python scripts/smoke.py` with database configured and with `DATABASE_URL`
  unset — API/web health, production home page and readiness contracts passed.
- `git diff --check` — passed.

No test or acceptance databases remained. The disposable Compose service and volume
were removed after verification. Other services and local environment files were
untouched. No live AWS or paid model calls were made.

## Limits and next slice

After proving child death and active-lease refusal, the harness advances only that
job's expiry in its owned database instead of waiting 660 seconds. It does not
change the original deadline or production lease policy. Commit-barrier SIGKILL
covers precise crash points, not arbitrary power/storage failure. SDK stubs verify
adapter contracts, not actual AWS delivery/IAM/redrive/retention. Abrupt parent
termination or database loss can prevent disposable-resource cleanup.

Accepted profile, cooperative budget, snapshot, external-effect, quarantine and
operations limitations remain listed in [the closure audit](PHASE_5.md). They do
not justify adding another independent Phase 5 feature to this acceptance slice.
Production/live AWS and hosted retry claims remain explicitly unverified/deferred.

Recommended next slice after review and separate authorization: Phase 6A, durable
approval requests and pause/resume for one controlled patch proposal. Establish
no write before approval and rejection preventing action; keep mutation gated
until the approval boundary is implemented and reviewed. Stop here for closure review.
