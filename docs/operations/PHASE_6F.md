# Phase 6F handoff — browser acceptance and closure

Verified 2026-10-01. **Phase 6 implementation and acceptance are complete within
the documented local scope, ready for closure review.** Phase 7 is not started.
No commit or push was made.

## Scope and outcome

Started from a clean repository. Reviewed AGENTS.md, the charter's Phase 6 gates,
roadmap, architecture, accepted approval/console boundaries, Phase 6E handoff and
the real console/proxy/worker implementation. The only remaining gate was the
browser-to-worker demonstration. Existing behavior passed without code changes.
No new tests, dependencies, migrations, abstractions or architectural decisions
were added. Existing ADRs 0021–0025 cover the demonstrated behavior.

The [closure audit](PHASE_6.md) maps each criterion to observed evidence and limits.
Both scenarios used the actual production Next UI, local proxy, authenticated
FastAPI, migrated PostgreSQL and fresh `runveil_worker.patch_worker` CLI processes.
The browser supplied both decisions; there were no direct decision API calls,
database edits, mocked browser responses, altered deadlines or lease bypasses.

Approval run: `3a2fb3f1-e1d2-4d15-b7bb-92861a76e8b3`.
Rejection run: `050be013-8936-4bb1-bc35-86dd4c7b26b8`.
Both used public text, one ordinary `a.txt` and the existing offline patch profile.

Before decisions, both runs paused with released leases, no mutation intent and
unchanged files; even a worker with a write grant was not selected. Browser
approval preserved the unchanged file until a fresh authorized worker performed
one exact replacement. A duplicate worker was not selected. Browser rejection
prevented selection and writing, with no mutation intent. Refresh showed both
persisted outcomes. Invalid-token refusal, inspection acknowledgement, run-switch
invalidation, Forget and reload clearing were also observed in the real browser.

## Files

Created:

- `docs/operations/PHASE_6.md`: criterion/evidence mapping, reproduction and limits.
- `docs/operations/PHASE_6F.md`: this handoff.
- `docs/operations/evidence/phase6/browser-acceptance.json`: sanitized database/file snapshots.
- `docs/operations/evidence/phase6/approved-before-worker.png`.
- `docs/operations/evidence/phase6/approved-applied.png`.
- `docs/operations/evidence/phase6/rejected-no-mutation.png`.

Modified: `ROADMAP.md`, `ARCHITECTURE.md`, `README.md`,
`docs/operations/DEVELOPMENT.md`, `APPROVAL_CONSOLE.md`, and `PHASE_6E.md` to link
closure evidence and supersede the prior acceptance gap without erasing history.

## Verification

Python 3.12.14, uv 0.12.19, Node 24.19.0, Codex in-app browser. Source commit was
`2ec2dc477a69fa7bae2947f6e686086fedb0ce5d`; application code stayed unchanged.
PostgreSQL ran under Compose project `runveil-phase6-checks` on loopback port 54329,
with explicit local user/database `runveil` and the documented development password.
The browser demonstration created and migrated its own randomly named
`runveil_acceptance_*` database and two private temporary checkouts. The generated
operator credential was passed through a private temporary file into browser-tool
memory without printing it. It never entered source, saved evidence or server logs.
The browser tab, servers, database, files and credential were removed afterward.

Checks and results:

- `npm run build` — production build passed and was used for browser acceptance.
- Real-browser sequence described above — passed both charter paths and supporting
  UI checks; three full-page screenshots and database/file snapshots retained.
- `uv run ruff format --check .`; `uv run ruff check .`; `uv run mypy` — passed;
  95 Python source files checked by mypy.
- `RUNVEIL_TEST_DATABASE_URL=… uv run pytest` — **284 passed**, including 149
  PostgreSQL integration cases, no skips.
- `RUNVEIL_TEST_DATABASE_URL=… uv run python scripts/phase5_acceptance.py` — passed
  actual process-death recovery, uncertain-intent failure, lease deferral and
  duplicate acknowledgement, with disposable DB cleanup.
- `npm run lint`; `npm run typecheck`; `npm test` — passed; six web tests.
- `DATABASE_URL=… uv run alembic upgrade head`; `DATABASE_URL=… uv run alembic check`
  — passed; no new upgrade operations detected.
- `DATABASE_URL=… uv run python scripts/smoke.py` and
  `env -u DATABASE_URL uv run python scripts/smoke.py` — passed real API/web health,
  production page/framing/referrer headers and both readiness states.
- `npm run format:check`; `git diff --check` — passed.

An initial coordinator startup failed before DB creation because Git launched from
Python resolved an incompatible macOS developer-tools binary. Resolving the source
commit in the working shell and passing it as metadata fixed setup; no application
change or security bypass was involved. No unresolved acceptance or check failure
remains. Dependency installs were not repeated because manifests/lockfiles and
installed dependencies were unchanged. No live provider/AWS test was performed.

## Review and next step

The prior Phase 6E browser gap is closed. This is acceptance evidence for the
existing local scope, not a new browser automation framework or cross-browser
compatibility certification. The trusted-checkout, shared-operator and uncertain
mutation limitations in the [closure assessment](PHASE_6.md) remain explicit.

Review Phase 6 closure. After separate authorization, choose a focused Phase 7
observability slice from the charter and roadmap. Stop here; do not add product
features, begin Phase 7, commit or push automatically.
