# Phase 10D handoff — approved sandbox application and validation

Date: 2026-10-02. Implemented; stop for review. No commit or push.

## Scope and decisions

Inspected the clean repository at `2d9cd43`, root AGENTS.md, charter, architecture,
roadmap, accepted sandbox/approval/mutation ADRs, completed 10C implementation and
handoff, and current development/CI requirements. This slice advances exact review
to controlled application and validation of one approved clamp repair. It does
not close the several-task acceptance gate for Phase 10.

New `sandbox-patch-v1` runs pin version-14 configuration/checkpoints and WRITE,
READ and EXECUTE capabilities. Their human approval explicitly permits applying
and testing the exact proposal in a fresh disposable fixture. Existing version-13
review-only approvals remain non-writing and cannot be adopted. The operator must
separately supply EXECUTE and WRITE for approved continuation; the model never gets
an apply_patch offer and cannot choose a command, path, image or environment.

Core obtains approved proposal/inspection evidence through a fenced store boundary,
commits one `repository.apply_patch` intent, then invokes the bound sandbox writer.
The existing single-mutation database index is reused. Before create and start,
persistence rechecks exact intent, approval/provenance, grants, lease/history and
deadline. Docker calls stay outside transactions. The runner compares the complete
three-file workspace and exact preimage, atomically replaces clamp.py, runs bounded
fixed tests and verifies postimage/directory entries. Only stdin JSON crosses into
the container. No host checkout is mounted or modified.

A confirmed result retains exact approved diff, proposal and workspace digests,
application status, test observation and cleanup evidence. A failed test, timeout
or output limit records a successful mutation observation in a FAILED task,
retaining its evidence. An unconfirmed/malformed outcome, postimage drift or expiry
during a possible mutation records uncertainty. An unresolved mutation terminates
as `sandbox_patch_outcome_unknown`, without a Docker binding or replay. Approval
waiting retains the original deadline/accounting; terminal duplicates do nothing.

See [ADR 0035](../adr/0035-approved-sandbox-patches.md) and
[operator commands](SANDBOX.md#approved-sandbox-patch-and-validation--phase-10d).

## Files

Created:

- `packages/agent_core/src/runveil_core/sandbox_patch.py`: exact input, bounded
  observation/result, narrow writer protocol and intersected grants.
- `packages/persistence/src/runveil_persistence/sandbox_mutations.py`: independent
  approved profile/checkpoint/proposal/preimage provenance validation.
- `apps/worker/src/runveil_worker/sandbox_patch_worker.py`: pinned profile,
  submit/work/inspect/decision CLI and terminal-only uncertain recovery.
- `packages/persistence/tests/test_sandbox_patch_worker.py`: consequential
  authorization, mutation, recovery, validation and real-container boundaries.
- `docs/adr/0035-approved-sandbox-patches.md`, this handoff, and
  `docs/operations/evidence/phase10d/{boundary,patch,recovery}.json`.

Modified:

- `packages/agent_core/src/runveil_core/{runtime,tools}.py`: narrow version-14
  execution and explicit unknown-mutation diagnostic.
- `packages/agent_core/tests/test_sandbox_review_contracts.py`: one bounded exact
  input/grant test, retaining existing review-only contracts.
- `packages/persistence/src/runveil_persistence/{execution,worker_approvals,traces}.py`:
  new profile binding, single-use intent/admission/outcome checks, conservative
  expiry/recovery, approval reuse mechanics and version-14 trace accounting.
- `packages/tool_runtime/src/runveil_tools/{sandbox,sandbox_execution}.py` and
  `sandbox/runner.py`: bounded stdin transport, fixed application/test operation,
  fresh pre/postimage validation and existing container lifecycle protections.
- `.github/workflows/ci.yml`: real approved-patch process and validation-boundary
  acceptance alongside existing sandbox tests.
- `README.md`, `ARCHITECTURE.md`, `ROADMAP.md`, ADR 0034's follow-up link and
  `docs/operations/{DEVELOPMENT,SANDBOX,WORKER}.md`: current boundaries/operations.

No schema migration, dependency, lockfile, API/UI or evaluation artifact changed.

## Verification

Python 3.12 and Node 24.19.0; Docker Desktop Linux ARM64. Dedicated
`runveil-phase10d` Compose project on loopback port 55432, with explicit local-only
user/database/password settings. Random test databases were created/migrated/dropped
by the existing fixtures. Unrelated services and prior acceptance volumes were left
untouched. The verification service was stopped afterward; acceptance data remains
in `runveil-phase10d_postgres_data`. No sandbox containers remain. Final reviewed image:

```text
sha256:c9459831a18dc6324b4953f94db1ac77b2cb855c8414f3d699794859d2b4eef6
```

| Command                                                                                                                                 | Result                                                                                              |
| --------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| `uv run ruff format --check .`                                                                                                          | Passed                                                                                              |
| `uv run ruff check .`                                                                                                                   | Passed                                                                                              |
| `uv run mypy`                                                                                                                           | 129 source files passed                                                                             |
| `uv run pytest -m 'not integration' -q`                                                                                                 | 153 passed                                                                                          |
| `RUNVEIL_SANDBOX_IMAGE="$SANDBOX_IMAGE" uv run pytest -m integration -q`                                                                | 190 passed; all four real-Docker tests enabled                                                      |
| `uv run alembic upgrade head` / `uv run alembic check`                                                                                  | Passed; no schema drift                                                                             |
| `docker build --network=none -t runveil-sandbox:phase10d sandbox`                                                                       | Passed                                                                                              |
| `uv run python scripts/phase10_sandbox_acceptance.py --image "$SANDBOX_IMAGE" --output docs/operations/evidence/phase10d/boundary.json` | Isolation, failed baseline, watchdog, output limit and cancellation passed                          |
| `uv run python scripts/phase5_acceptance.py`                                                                                            | Real process-death checkpoint recovery, uncertain intent, live-lease deferral and duplicates passed |
| `npm run format:check`, `npm run lint`, `npm run typecheck`                                                                             | Passed                                                                                              |
| `npm test`                                                                                                                              | 11 tests passed                                                                                     |
| `npm run build`                                                                                                                         | Passed                                                                                              |
| `uv run python scripts/smoke.py`                                                                                                        | API/web health, production approval/trace routes and protections, database readiness passed         |
| `git diff --check`                                                                                                                      | Passed                                                                                              |

The new focused tests cover missing WRITE, image drift, preapproval dispatch
prevention, rejection and review-only isolation; exact durable intent and independent
postimage checks; lost-lease admission/late outcomes; interruption before effect,
after effect and after committed outcome; mid-mutation deadline expiry; preserved
failed-validation evidence/accounting; and one real fresh-process approved repair.
A real-container exercise checks both changed target preimage and other-workspace
bytes, failed tests, test timeout, bounded output, modified tests and extra entries,
with confirmed container absence. Existing tests continue to cover host mutation,
approvals, cancellation/cleanup, observability, evaluation and statistics boundaries.

Additional retained evidence:

- [Boundary acceptance](evidence/phase10d/boundary.json) against the final image.
- [Fresh CLI application/rejection](evidence/phase10d/patch.json): exact proposal,
  approval, passed real tests, approved diff, changed workspace digest, mutation
  outcome, trace accounting, content-free mutation span, duplicate refusal and
  explicit container-absence checks.
- [Real post-effect process death](evidence/phase10d/recovery.json): a controlled
  fault held the worker after real Docker application/tests/cleanup but before
  outcome commit. SIGKILL left the mutation REQUESTED. After explicitly expiring
  its lease in the dedicated acceptance database, a fresh CLI process without
  image or grants recorded unknown outcome. Three total tool calls and no new
  mutation prove no replay; inspection reports application as unknown.

The CLI and SIGKILL exercises used temporary local fault/acceptance drivers. The
supported workflow commands are in SANDBOX.md; the core boundaries and real
application/validation tests are maintained in pytest and CI. No live paid provider
or AWS service was called.

## Limits and next slice

The patch exists durably as approved text/diff and evidence, not a retained modified
checkout. This is one scripted public clamp repair, not model quality, a hidden
benchmark or several-task Phase 10 closure. Approval HTTP/UI support remains
limited to prior profiles; the trusted local operator CLI owns this workflow.

Docker daemon/image trust, shared-kernel isolation and non-atomic admission fences
remain explicit. Tests execute proposed code only inside the disposable container;
pass/fail is an observation, not a proof against malicious code. No hostile
multi-tenant claim, automatic rollback, cleanup reconciler or exactly-once external
effect is introduced. Crash cleanup remains operator-owned. Covered implementation
identity changes intentionally refuse clean continuation of older unfinished
sandbox runs; uncertain terminal recovery does not construct an adapter.

After review, extend controlled fixture/task selection to several small repairs
with deliberately pinned identities and independent end-to-end acceptance. Audit
remaining search and failed-task inspection requirements before Phase 10 closure.
Keep review-only approval isolation and single-use/no-replay mutation semantics.
