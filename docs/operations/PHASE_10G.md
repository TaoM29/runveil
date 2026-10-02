# Phase 10G handoff: sandbox-bound repository search and closure review

Date: 2026-10-02. Base: `d8f2ac0` (`feat: broaden sandbox coding task acceptance`).
No commit or push. This is the final planned Phase 10 implementation slice;
[closure review](PHASE_10.md) remains a human gate.

## Implementation and decisions

The charter's original Phase 10 checklist requires search as well as inspection.
The v15 workflow completed the three-task gate but did not dispatch sandbox search.
Version 16 / `software-engineering-v2` now connects inspect → search → failing
baseline → exact proposal → human approval → controlled application/post-change
tests. A separate `software_search_worker` CLI preserves old v15 enrollment and
configuration. The scripted provider searches `return` and uses the source hit to
select its known repair. This is controlled integration evidence, not model quality.

Search is a pure bounded literal scan of the immutable three-file snapshot already
produced inside the sandbox. It has no host filesystem, subprocess, command, regex,
network or arbitrary path authority. Input is 1–128 characters without CR/LF/NUL;
results are limited to ten ordered path/one-based-line matches with 160-character
excerpts, truncation and the inspection digest. Both pinned and operator policies
must grant the tool and READ. The underlying runner and fixtures are unchanged.

Search intent and outcome use existing durable execution, budgets and fences.
Persistence independently recomputes the result against the recorded inspection,
source model action/context, pinned task and event order. Approval and mutation
checks require that same search evidence in baseline/proposal model contexts.
Completed search checkpoints are reused; unresolved search intent terminates
without replay or Docker. Explicit WRITE/EXECUTE, exact approvals, single-use
mutation intent, workspace/preimage revalidation and uncertain-mutation recovery
remain shared with prior profiles.

Nine steps/four model/five tool calls retain the original one-hour and token limits.
The new cost ceiling is 125,000 nanodollars: four scripted calls consume 100,000,
which would hit the previous strict budget boundary. The focused recovery check
caught that edge; only v16's fixed cost ceiling changed. See
[ADR 0038](../adr/0038-sandbox-evidence-search.md).

## Files created and modified

Created:

- `packages/agent_core/src/runveil_core/sandbox_search.py`: search contracts,
  explicit authorization, deterministic bounded scan and model offer.
- `packages/persistence/src/runveil_persistence/sandbox_search.py`: independently
  recomputed durable search and model-context provenance.
- `apps/worker/src/runveil_worker/software_search_worker.py`: v16 local entry point.
- `packages/agent_core/tests/test_sandbox_search_contracts.py` and
  `packages/persistence/tests/test_sandbox_search_workflow.py`: focused bounds,
  authorization, forgery, checkpoint reuse and no-replay checks.
- ADR 0038, this handoff and `evidence/phase10g/{tasks,boundary}.json`.

Modified:

- Core `runtime.py` and `software.py`: exact v16 grants, ordered search stage and
  shared approval/mutation/recovery handling.
- Persistence `execution.py`, `worker_approvals.py`, `sandbox_mutations.py` and
  `traces.py`: version admission, outcome validation, approval/mutation evidence
  revalidation and trace support.
- Tool runtime `sandbox_execution.py`: search module in implementation identity.
- Worker `sandbox_patch_worker.py`: v16 configuration/provider/CLI selection and
  local inspection of durable tool requests as well as outcomes.
- `packages/persistence/tests/test_software_worker.py`: existing real-Docker matrix
  covers both profiles and all three tasks; existing recovery/WRITE-denial cases
  cover both profiles. No separate parallel testing framework.
- README, ARCHITECTURE, ROADMAP, DEVELOPMENT, WORKER, SANDBOX and PHASE_10 audit:
  current operation, boundaries and bounded-scope closure assessment.

No migration, dependency, runner, fixture, API/UI, remote broker or paid provider
change. Existing CI already selects the expanded real-Docker test matrix.

## Verification

Local verification uses Compose project `runveil-phase10g`, port 55432, the
repository's documented local-only credentials, and Node 24.19.0. Test databases
are randomly named and disposed by the existing harness. Reviewed image:

```text
sha256:d786a5117ba0e84575926d6cb46ed7461e46a01a08db8eb64e138f6769395ba4
```

| Command                                                                                                                                 | Result                                                                                          |
| --------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| `uv run ruff format --check .` / `uv run ruff check .`                                                                                  | Passed                                                                                          |
| `uv run mypy`                                                                                                                           | 138 source files passed                                                                         |
| `uv run pytest -m 'not integration' -q`                                                                                                 | 155 passed                                                                                      |
| `RUNVEIL_SANDBOX_IMAGE="$SANDBOX_IMAGE" uv run pytest -m integration -q`                                                                | 212 passed; all eleven real-Docker cases enabled                                                |
| `uv run alembic upgrade head` / `uv run alembic check`                                                                                  | Passed; no schema drift                                                                         |
| `docker build --network=none -t runveil-sandbox:phase10g sandbox`                                                                       | Passed                                                                                          |
| `uv run python scripts/phase10_sandbox_acceptance.py --image "$SANDBOX_IMAGE" --output docs/operations/evidence/phase10g/boundary.json` | Passed: isolation, failing baseline, watchdog, output limit and cancellation                    |
| `uv run python scripts/phase5_acceptance.py`                                                                                            | SIGKILL checkpoint/uncertain-intent recovery, live-lease deferral and duplicate handling passed |
| `npm run format:check`                                                                                                                  | Passed                                                                                          |
| `npm run lint` / `npm run typecheck` / `npm test` / `npm run build`                                                                     | Passed; 11 frontend tests                                                                       |
| `uv run python scripts/smoke.py`                                                                                                        | API/web health, production pages/protections and readiness passed                               |
| `git diff --check`                                                                                                                      | Passed                                                                                          |

Fresh CLI processes additionally submit, inspect, work, approve/reject and continue
all three tasks against the retained local database. The acceptance checks exact
fixture text, search query/path/line/excerpt/digest, exact patch and full postimage
against independent oracles. Approved runs must pass fixed tests, rejected runs
must have no mutation, and duplicate terminal work must do nothing. It checks
absence of each owned container. [Task evidence](evidence/phase10g/tasks.json)
retains the ordered requests/outcomes, identity, diff and decision for six runs.
The same behavior is reproducible through the real-Docker pytest matrix. The retained
CLI run additionally checks full excerpts; unit coverage checks truncation, long-line
excerpts, literal matching and missing grants. A final focused rerun after adding
requests to local inspection passed 15 deterministic persistence cases (seven Docker
cases deselected); the separately retained fresh-process runs include those requests.

## Closure, concerns and next slice

All original implementation checklist items and acceptance criteria are now
represented and verified within the three public scripted fixtures. Recommend
bounded-scope Phase 10 closure after review. The [audit](PHASE_10.md) preserves the
original requirements and distinguishes workflow mechanics from general model
repair quality. The previous failed-validation evidence remains linked; existing
postimage/validation boundary regressions still run in the full suite.

Search sees the original saved snapshot, not a current checkout or post-change
workspace. Mutation still independently checks the entire original preimage.
Default fixed tests are observations, not proof against malicious repair code.
Docker's trusted image/daemon, shared kernel, admission-not-revocation semantics
and manual crash cleanup limitations remain. No hosted provider or remote CI ran.
Covered implementation changes invalidate old live bindings: continue those with
their original installation or submit new runs; never repin a job. Uncertain-intent
terminal recovery remains binding-free.

Verification data is retained in `runveil-phase10g_postgres_data`; the dedicated
Compose service is stopped and no labelled sandbox containers remain. Other project
services and volumes are untouched.
Next: review this slice and the closure audit. Only after acceptance and separate
authorization, plan the first coherent Phase 11 MCP slice. Stop for review.
