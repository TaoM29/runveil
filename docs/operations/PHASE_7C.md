# Phase 7C handoff — execution telemetry

Implemented and verified 2026-10-01. Review pending. No commit or push.

## Implementation and decisions

Started from a clean checkout. Inspected AGENTS.md, the charter, architecture,
roadmap, relevant accepted ADRs, completed Phase 6/7A/7B evidence, runtime dispatch,
worker entry points, durable trace contracts, mutation fingerprints, CI and the
development guide. The roadmap's next coherent slice was opt-in OpenTelemetry and
safe structured correlation around existing execution. No scope conflict arose.

The core now uses only the OTel API, with explicit scoped tracers disabled by
default. Execute roots and model/read-tool/approved-patch child spans correlate
with durable run/invocation IDs and committed intent event positions. Root
accounting preserves unknown usage/cost. Each retry/resume has a new root; spans
never pretend to survive process death. No exception events or content are captured.

Worker CLIs own SDK setup and shutdown. `RUNVEIL_TELEMETRY=json` selects bounded
batch JSON stderr output with an independent metadata allowlist. Original status
output remains on stdout. No collector, global provider, ambient propagation,
resource-environment import, new authorization or network exporter is installed.
The trace UI remains operational over persisted evidence with unchanged read-only
and credential boundaries. No database migrations, event/checkpoint schemas,
execution profiles, tool fingerprints, API routes or UI code changed.

[ADR 0028](../adr/0028-execution-telemetry.md) records the choice; the
[operations guide](TELEMETRY.md) defines setup, timing/outcome semantics, privacy and
loss/shutdown limitations. OTel API/SDK 1.45.0 and semantic conventions 0.66b0 are
locked supporting dependencies; runtime execution remains project-owned.

## Files created

- `packages/agent_core/src/runveil_core/telemetry.py`: guarded scoped observations.
- `apps/worker/src/runveil_worker/telemetry.py`: SDK lifecycle and bounded JSON exporter.
- `packages/agent_core/tests/test_telemetry.py`: two focused isolation/cancellation tests.
- `packages/persistence/tests/test_telemetry_execution.py`: two durable correlation/failure tests.
- `docs/adr/0028-execution-telemetry.md`.
- `docs/operations/TELEMETRY.md`.
- `docs/operations/PHASE_7C.md`: this handoff.

## Files modified

- `packages/agent_core/src/runveil_core/runtime.py`: observation around existing boundaries.
- `apps/worker/src/runveil_worker/__main__.py`, `review_worker.py`, `patch_worker.py`,
  `sqs.py`: opt-in CLI lifecycle only.
- `packages/persistence/tests/test_patch_worker.py`: enable tracing in the existing
  approval/grant/profile/single-apply scenario; assert observed boundaries.
- `packages/agent_core/pyproject.toml`, `apps/worker/pyproject.toml`, `uv.lock`: API/SDK dependencies.
- `README.md`, `ARCHITECTURE.md`, `ROADMAP.md`, `docs/operations/DEVELOPMENT.md`:
  current behavior, references and next gate.

## Verification

Python 3.12.14, uv 0.12.19 and Node 24.19.0. A newly created Compose project
`runveil-phase7c-checks` owned the PostgreSQL service/volume on loopback port 54329.
Integration tests and process-death acceptance created/dropped their own temporary
databases. CLI acceptance used only this task's disposable `runveil` database.
No existing database was reset, and no live provider, paid service or AWS call ran.

Environment for commands below:

```sh
export PATH=/Users/taom/.nvm/versions/node/v24.19.0/bin:$PATH
export POSTGRES_USER=runveil POSTGRES_DB=runveil
export POSTGRES_PASSWORD=runveil-local-only POSTGRES_PORT=54329
export DATABASE_URL='postgresql+psycopg://runveil:runveil-local-only@127.0.0.1:54329/runveil'
export RUNVEIL_TEST_DATABASE_URL='postgresql+psycopg://runveil:runveil-local-only@127.0.0.1:54329/postgres'
```

- `uv lock`; `uv sync --locked --all-packages`; `npm ci` — passed.
- `docker compose -p runveil-phase7c-checks up -d --wait --wait-timeout 90` — passed.
- `uv run alembic upgrade head`; `uv run alembic check` — passed; no new operations.
- `uv run ruff format --check .`; `uv run ruff check .`; `uv run mypy` — passed;
  103 typed source files.
- Focused telemetry/patch-worker selection — **10 passed**, then full
  `uv run pytest` — **293 passed**, no skips, in 86.72 seconds.
- `uv run python scripts/phase5_acceptance.py` — passed real SIGKILL checkpoint
  recovery, uncertain-intent failure, active-lease deferral and duplicate acknowledgement.
- `npm run lint`; `npm run typecheck`; `npm test`; `npm run build` — passed;
  **11 web tests** and production build.
- `uv run python scripts/smoke.py`; `env -u DATABASE_URL uv run python scripts/smoke.py`
  — passed real API/web HTTP, production approval/trace pages and security headers,
  and both database readiness states.
- `npm run format:check`; `git diff --check` — passed after documentation updates.

The four new tests exercise concurrent root/child identity, cancellation and
original-exception preservation, throwing span callbacks, real batch exporter
output errors, retry intent/accounting reconciliation, and accidental SDK payload/
exception rejection at export. The existing approved-write test verifies telemetry
adds no WRITE grant, review-profile escalation or second mutation. Existing full
API/proxy/component tests continue to exercise authentication and read-only boundaries.

A temporary coordinator invoked fresh `python -m runveil_worker submit` and
`work --once --run-id … --profile fixture-calls-v1` processes with telemetry disabled
and enabled. Both succeeded; disabled stderr was empty. Enabled output contained
exactly four JSON records: one root, two model children and one tool child, sharing
a trace ID and correct parent IDs. Run ID, token totals and cost matched `read_trace`
from PostgreSQL. An environment resource sentinel was omitted. The coordinator
was removed rather than added as another test framework.

No unresolved verification failure. Dependency installation reported existing npm
ESLint deprecation and optional install-script notices; lint/typecheck/tests/build
passed without changing frontend dependencies. No new browser session was needed
for this backend-only slice; Phase 7B's actual browser evidence remains the UI
acceptance evidence. Collector delivery and real hosted instrumentation were not tested.
Task-owned Compose service/volume were removed after checks with
`docker compose -p runveil-phase7c-checks down --volumes`.

## Remaining boundaries and next slice

Output is best effort: a bounded queue can drop records; crashes can omit active
spans; root completion precedes worker finalization. Local dispatch timing is not
persisted duration or pure provider latency. Failed output cannot trigger retries.
A stalled sink can delay CLI shutdown by the SDK join (up to 30 seconds), and its
export-timeout parameter cannot forcibly interrupt a blocked write. Arbitrary
library-supplied tracers remain trusted synchronous configuration.

Claim/admission, operator decisions and uncertain-patch cleanup outside core execute
are not spanned. No metrics, collector, cross-process trace propagation, run discovery,
dashboard or telemetry-based authority was added. Per-attempt UI usage/latency
projection remains deferred. Phase 7 is not declared complete.

Next: review this slice, then audit Phase 7 acceptance across completed, failed,
retried and approval-wait runs, reconciling UI evidence, persisted events and
optional telemetry. Address only demonstrated acceptance gaps before proposing
Phase 7 closure. Phase 8 remains outside scope. Stop for review.
