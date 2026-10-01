# Phase 6E handoff — local approval console

## Review status

Implemented on 2026-10-01; stop for review. No commit or push was made. Started from
a clean working tree and inspected root/web instructions, the charter, roadmap,
architecture, accepted approval/mutation ADRs, Phase 6D implementation, development
checks and the installed Next.js guides before editing.

This is the planned small operational UI slice. The page accepts one known run ID
and operator token, displays exact proposal/workspace/mutation evidence, and offers
inspection-bound approve/reject. Core, API, persistence, worker and migration code
are unchanged. It does not submit work, dispatch a worker, grant WRITE, broaden
profile authority or change workspace/mutation/recovery guarantees.

## Implementation and trade-offs

- A client component holds credentials/inspection only in memory. Forget and
  pagehide clear them. Input changes invalidate inspection and pending responses.
- Exact before/after text is rendered without HTML interpretation; a full JSON
  disclosure escapes whitespace and non-ASCII characters for unambiguous inspection.
  Profile consequences distinguish review completion from permission for later
  controlled replacement. Approval and mutation outcome are separate displays.
- Both decisions require inspection acknowledgement and send the observed profile,
  approval ID, revision and digest. No automatic polling or retries. Failed or
  interrupted decisions warn that the outcome may be unknown and require inspection.
- The same-origin Next route forwards only the caller's bearer to an explicitly
  configured loopback API origin. It rejects foreign Host/Origin, arbitrary paths,
  missing credentials and oversized requests. It denies redirects, strips upstream
  headers/cookies, bounds response bodies/time and returns fixed no-store errors.
- Console headers deny framing and suppress referrers. No cookie authentication,
  browser storage, server credential or remote proxy deployment is introduced.
- jsdom is the only added direct dependency, development-only, for focused React DOM
  lifecycle tests. The npm manifest/lockfile are consistent. No production library,
  generalized client abstraction or new Python dependency is added.

See [ADR 0025](../adr/0025-local-approval-console.md) and
[console operations](APPROVAL_CONSOLE.md) for the local security/operational contract.

## Files created and modified

Created:

- `apps/web/app/approval-console.tsx`
- `apps/web/app/api/approvals/[runId]/route.ts`
- `apps/web/lib/approval.ts`
- `apps/web/next.config.ts`
- `apps/web/tests/approval-console.test.tsx`
- `apps/web/tests/approval-proxy.test.ts`
- `docs/adr/0025-local-approval-console.md`
- `docs/operations/APPROVAL_CONSOLE.md`
- `docs/operations/PHASE_6E.md`

Modified:

- `apps/web/app/page.tsx`, `apps/web/app/layout.tsx`
- `apps/web/package.json`, `package-lock.json`
- `scripts/smoke.py`
- `README.md`, `ARCHITECTURE.md`, `ROADMAP.md`
- `docs/operations/DEVELOPMENT.md`, `APPROVAL_API.md`, `APPROVALS.md`, `PATCHES.md`

## Verification and findings

Python 3.12.14, uv 0.12.19, Node 24.19.0. PostgreSQL ran under isolated Compose
project `runveil-phase6-checks`, explicit user/database `runveil`, port 54329 and
the documented local-only password. Database fixtures and the one-off acceptance
check created/migrated/dropped only randomly named test databases. No hosted model,
live AWS or paid provider calls occurred.

Commands/results:

- `uv sync --locked --all-packages` — passed.
- `npm ci` — passed, zero reported vulnerabilities. Existing ESLint deprecation
  and fsevents/unrs-resolver install-script policy warnings remain; no script
  authorization or unrelated upgrade was made.
- `uv run ruff format --check .`; `uv run ruff check .` — passed.
- `uv run mypy` — passed, 95 source files.
- `DATABASE_URL=… uv run alembic upgrade head`; `DATABASE_URL=… uv run alembic check`
  — passed; no new upgrade operations detected.
- `RUNVEIL_TEST_DATABASE_URL=… uv run pytest` — **284 passed**, including all 149
  PostgreSQL integration tests; no skips.
- `RUNVEIL_TEST_DATABASE_URL=… uv run python scripts/phase5_acceptance.py` — passed
  actual process-death checkpoint recovery, uncertain-intent failure, lease deferral,
  duplicate acknowledgement and disposable database cleanup.
- `npm run lint`; `npm run typecheck`; `npm test`; `npm run build` — passed.
  **Six web tests** (five new focused cases, one existing health test) passed.
- `npm run format:check`; `git diff --check` — passed.
- `DATABASE_URL=… uv run python scripts/smoke.py` and
  `env -u DATABASE_URL uv run python scripts/smoke.py` — passed actual API/web health,
  production home page, framing/referrer headers and both readiness states.
- A one-off Python acceptance harness outside the repository started production
  Next/Uvicorn against a newly migrated test DB, generated an ephemeral in-memory
  token, and created two paused patch workers in temporary checkouts. Through the
  web proxy it verified unauthenticated/origin/stale refusal, exact inspection,
  approve/reject decisions, duplicate refusal and unchanged files before worker
  execution. A separately authorized worker applied the approved text; rejection
  prevented selection/writing. Subsequent proxy inspection reported the successful
  mutation. Server logs did not contain the token. Processes, DB and checkouts were
  cleaned up. This was a real HTTP integration check, not a browser E2E suite.
- The production page was opened in the in-app browser and its initial visual and
  accessibility layout inspected. The temporary preview/tab were then closed.

The real-server check caught a genuine integration issue: Next normalizes its
internal request URL hostname, so comparing Origin against that URL incorrectly
rejected a legitimate `127.0.0.1` request. The proxy now validates the local Host
header and compares Origin to it, never trusting forwarded host headers; a
regression assertion and rerun of the real server flow passed. An initial React
cleanup lint warning was also resolved. No unresolved check failure remains.

DOM tests exercise escaped text, acknowledgement, exact decision payloads,
unknown outcomes without retry, foreign-run response refusal, stale responses,
input changes during requests/decisions, forgetting and pagehide. Proxy tests cover
caller-only credential forwarding, no cookies/locations, foreign origin/host,
invalid destination/path/auth, body limits, stalled input/response timeout and
non-reflecting errors. Backend tests continue to cover transactional approval,
write-grant denial, provenance, durability and workspace-integrity boundaries.

## Remaining limits and next slice

This remains a local shared-operator capability, not individual reviewer identity,
tenant isolation, remote deployment or a hardened browser sandbox. Password managers,
extensions and hostile same-origin scripts are outside the memory-only guarantee.
A transport abort cannot revoke a decision already committing; reinspection is
required. Workspace fingerprints are pinned identities, not live file verification.
Mutation uncertainty must never be interpreted as proof of unchanged files.

Full-browser approve/reject interaction against the real worker has not been run:
interaction/race coverage uses React DOM tests, while actual HTTP execution is
verified separately. The UI slice is ready for review, but final Phase 6 closure
is not claimed. Recommended next slice: consolidate the Phase 6 acceptance mapping
and run that full-browser demonstration without expanding the UI, then stop for
closure review before Phase 7.

## Subsequent browser acceptance — complete

Phase 6F on 2026-10-01 closed the browser gap recorded above without changing
application behavior. Both approve/apply and reject/no-mutation paths passed
through the real browser, production web/API, database and fresh CLI workers.
See [closure assessment](PHASE_6.md), [screenshots and snapshots](evidence/phase6/)
and [Phase 6F handoff](PHASE_6F.md). The original slice's verification scope above
is retained as historical evidence.
