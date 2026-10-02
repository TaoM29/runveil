# Phase 10C handoff — sandbox inspection and exact proposals

Date: 2026-10-02. Implemented; stop for review. No commit or push.

## Scope and decisions

Inspected the completed Phase 9 closure, Phase 10A/10B implementation, current
roadmap, charter, architecture, accepted approval/sandbox ADRs and development/CI
requirements. The next authorized slice is inspection and exact review; applying
patches and repaired-task acceptance remain later work.

Added the separate `sandbox-review-v1` scripted worker and version-13 configuration/
checkpoint contract. A fixed empty-input inspection reads TASK.md, clamp.py and
test_clamp.py inside the pinned disposable Docker fixture. The existing container
isolation/resource/output limits, committed tool intent, pre-create/pre-start
ownership/deadline checks, cleanup and uncertain-intent recovery remain active.
No host repository mount or model-controlled command/path/image is introduced.

The proposal is an exact clamp.py replacement against the recorded inspection.
Core and persistence independently enforce preimage matching; the storage boundary
also checks that the complete successful inspection predates and appears in the
proposing model request. The existing atomic outcome/checkpoint/approval/pause
releases the lease. Inspection exposes exact text, immutable sandbox identity,
inspection/proposal digests, before/after hashes and a deterministic review diff.
Approval only resumes to a review-complete summary. No patch is applied.

See [ADR 0034](../adr/0034-sandbox-inspection-review.md) for the architectural
boundary and [operations](SANDBOX.md#sandbox-inspection-and-exact-review--phase-10c)
for reproducible submit/work/inspect/approve/reject commands.

## Files

Created:

- `packages/agent_core/src/runveil_core/sandbox_review.py`: bounded contracts,
  fixed offers/grants, exact preimage validation and diff rendering.
- `apps/worker/src/runveil_worker/sandbox_review_worker.py`: pinned profile,
  scripted proposal, conservative recovery and local operator CLI.
- `packages/agent_core/tests/test_sandbox_review_contracts.py` and
  `packages/persistence/tests/test_sandbox_review.py`: focused bounds, provenance,
  decisions, recovery, deadline and real-container coverage.
- `docs/adr/0034-sandbox-inspection-review.md`, this handoff and
  `docs/operations/evidence/phase10c/{boundary,review}.json`.

Modified:

- `packages/agent_core/src/runveil_core/runtime.py`: version-13 narrow dispatch
  and review suspension, preserving version-11-only write authorization.
- `packages/tool_runtime/src/runveil_tools/{sandbox,sandbox_execution}.py` and
  `sandbox/runner.py`: fixed inspection mode, strict UTF-8/bounded complete output,
  existing fenced disposable-container lifecycle and covered source identity.
- `packages/persistence/src/runveil_persistence/{execution,worker_approvals,traces}.py`:
  dedicated profile binding, independent durable preimage checks, review decisions
  and version-13 accounting projection.
- `packages/persistence/tests/test_sandbox_worker.py`: reusable stub response
  controls; the original baseline/fencing/recovery tests remain intact.
- `.github/workflows/ci.yml`: opt into both fresh-process Docker integration tests.
- `README.md`, `ARCHITECTURE.md`, `ROADMAP.md`,
  `docs/operations/{DEVELOPMENT,SANDBOX,WORKER}.md`: current boundary and operations.

No migration, dependency, lockfile, API/UI or evaluation-artifact changes.

## Verification

Local environment: Python 3.12, Node 24.19.0, Docker Desktop Linux ARM64. A dedicated
`runveil-phase10c` Compose project used loopback port 55432, with explicit local-only
user/database/password settings; unrelated running services were left untouched.
The dedicated service was stopped after verification. Its acceptance data remains
in `runveil-phase10c_postgres_data`; no sandbox containers remain.
The reviewed image used for all final Docker checks:

```text
sha256:09d00daf632b368aa055e3c63f84b6ec9a8731249e0927275c6c4a2e2fdb0b04
```

Successful checks:

| Command                                                                                                                                 | Result                                                                                     |
| --------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| `uv run ruff format --check .`                                                                                                          | Passed                                                                                     |
| `uv run ruff check .`                                                                                                                   | Passed                                                                                     |
| `uv run mypy`                                                                                                                           | 125 source files passed                                                                    |
| `uv run pytest -m 'not integration' -q`                                                                                                 | 152 passed                                                                                 |
| `RUNVEIL_SANDBOX_IMAGE="$SANDBOX_IMAGE" uv run pytest -m integration -q`                                                                | 178 passed; both real Docker tests enabled                                                 |
| `uv run alembic upgrade head` / `uv run alembic check`                                                                                  | Passed; no schema drift                                                                    |
| `uv run python scripts/phase5_acceptance.py`                                                                                            | Real SIGKILL recovery, uncertain intent and duplicate acknowledgement passed               |
| `docker build --network=none -t runveil-sandbox:phase10c sandbox`                                                                       | Passed                                                                                     |
| `uv run python scripts/phase10_sandbox_acceptance.py --image "$SANDBOX_IMAGE" --output docs/operations/evidence/phase10c/boundary.json` | Isolation, failing baseline, watchdog, output limit and cancellation passed                |
| `npm run format:check`, `npm run lint`, `npm run typecheck`                                                                             | Passed                                                                                     |
| `npm test`                                                                                                                              | 11 tests passed                                                                            |
| `npm run build`                                                                                                                         | Passed                                                                                     |
| `uv run python scripts/smoke.py`                                                                                                        | API/web health, production approval/trace pages, protections and database readiness passed |
| `git diff --check`                                                                                                                      | Passed                                                                                     |

The new integration coverage verifies missing operator authority and image drift
before dispatch, approval/rejection and stale/duplicate decisions, clean inspection
checkpoint continuation, uncertain inspection/proposal intent without adapter or
replay, forbidden model arguments/paths/invented preimages/incomplete output,
independent database refusal when core preimage validation is bypassed, unchanged
accounting and deadline expiry after approval. One small contract test covers
complete bounded UTF-8 evidence and missing-final-newline diff display. The existing
suite covers stale claims, cleanup failures, cancellation, authorization, host
mutation boundaries, traces and evaluations.

In addition, fresh local CLI processes exercised submit → work → inspect →
approve/reject → work → terminal duplicate on two real sandbox runs. The retained
[review evidence](evidence/phase10c/review.json) records exact inspection/proposal
identity and diff, terminal outcomes, two succeeded tool calls per run, trace
accounting, four content-free tool spans and explicit container-absence queries.
The [boundary report](evidence/phase10c/boundary.json) retains the original sandbox
acceptance against the same image. The CLI exercise used a temporary local driver;
the supported commands are documented in SANDBOX.md and fresh-process acceptance
is maintained in the integration test and CI.

## Limits and next slice

This is one trusted fixture with a scripted proposal, not a solved coding benchmark
or evidence of model quality. The existing approval HTTP API/browser console does
not accept this new profile; its trusted local CLI is the review interface. The
read-only trace projection understands version 13. No live provider/AWS acceptance
or hostile multi-tenant Docker guarantee is claimed.

The implementation fingerprint intentionally changes; unfinished older sandbox
runs can refuse fresh bindings. The operator-selected image/daemon remain trusted.
Admission fences cannot revoke already-sent Docker requests, and uncertain crash
cleanup remains operator-owned. Existing original deadline/accounting and
terminal-only recovery remain in force. No automatic replay or cleanup reconciler.

After review, the next coherent slice is a separately authorized sandbox patch
application contract, binding an exact approved proposal to a fresh pinned preimage,
durable intent and conservative uncertain-effect recovery. These review-only
approvals must never be adopted as write authority. Repaired-result verification
and several controlled tasks remain later Phase 10 acceptance work.
