# Phase 10E handoff — integrated fixture engineering workflow

Date: 2026-10-02. Implemented; stop for review. No commit or push.

## Scope and decisions

Started from clean commit `9e9161f` and inspected AGENTS.md, charter, architecture,
roadmap, accepted sandbox/approval/mutation ADRs, completed Phase 10D implementation
and handoff, and development/CI requirements. The current request prioritizes
connecting existing capabilities. This slice retains the single project-owned
clamp fixture; the roadmap's several-task expansion remains a separate review gate.

New `software-engineering-v1` runs pin configuration/checkpoint version 15 and
connect inspection → baseline tests → exact proposal → human approval → controlled
application and post-change tests. Only the next tool is offered before approval;
model-generated early success is refused. Three model calls and four tool calls
share the existing budgets and one-hour deadline. The scripted provider demonstrates
orchestration, not model repair quality.

A proposal requires a completed failing baseline (exit 1). Core enforces ordered
observations; persistence independently checks one recorded baseline, invocation
order, source model action and exact inspection/baseline context. These checks run
at pause, decision and mutation authorization. Unexpected passing baseline tests,
timeout or output limits preserve their observation in a FAILED run, without a
proposal. Existing infrastructure errors remain distinct.

The existing approved mutation path is reused: exact approved payload, single-use
intent, operator WRITE/EXECUTE, immutable sandbox binding, fenced admission,
full workspace/preimage checks, fixed post-change tests, digests/diff and confirmed
cleanup. Review-only profiles remain non-writing. No API/UI expansion, arbitrary
command, repository path, host mount or host code execution was added.

Local inspection now works for queued and failed tasks before approval, as well
as review and completion. It retains ordered tool evidence, exact proposal/diff,
validation and mutation uncertainty. Completed checkpoints reuse evidence; unknown
baseline/proposal intent terminates without replay, and unknown mutation still
terminates as `sandbox_patch_outcome_unknown` without a Docker binding. Old profiles
retain their authorities; they cannot consume the new profile's jobs or approvals.

See [ADR 0036](../adr/0036-fixture-engineering-workflow.md) and
[operator procedure](SANDBOX.md#fixture-engineering-workflow--phase-10e).

## Files

Created:

- `packages/agent_core/src/runveil_core/software.py`: closed workflow policy,
  next-tool selection and baseline predicate.
- `apps/worker/src/runveil_worker/software_worker.py`: dedicated CLI entrypoint.
- `packages/persistence/tests/test_software_worker.py`: seven behavioral cases
  covering failed baselines/early finish, forged or missing journal context,
  checkpoint reuse, uncertain baseline/mutation effects and real Docker workflows.
- `docs/adr/0036-fixture-engineering-workflow.md`, this handoff and
  `docs/operations/evidence/phase10e/{boundary,workflow}.json`.

Modified:

- `packages/agent_core/src/runveil_core/runtime.py`: version-15 policy, staged
  offers/dispatch, baseline terminal outcome and approved mutation reuse.
- `packages/persistence/src/runveil_persistence/execution.py`: dedicated profile,
  independent baseline/final-state checks and existing mutation fences/recovery.
- `packages/persistence/src/runveil_persistence/worker_approvals.py`: independent
  baseline provenance/context validation at pause and decisions.
- `packages/persistence/src/runveil_persistence/sandbox_mutations.py`: version-15
  profile/checkpoint binding, reusing existing exact approved payload validation.
- `packages/persistence/src/runveil_persistence/traces.py`: version-15 metadata.
- `packages/tool_runtime/src/runveil_tools/sandbox_execution.py`: include workflow
  policy source in the immutable implementation digest.
- `apps/worker/src/runveil_worker/sandbox_patch_worker.py`: shared concrete worker
  operations, new pinned configuration/scripted provider, complete local inspection.
- `.github/workflows/ci.yml`: opt into the real workflow test with other Docker tests.
- `README.md`, `ARCHITECTURE.md`, `ROADMAP.md` and
  `docs/operations/{DEVELOPMENT,SANDBOX,WORKER}.md`: current behavior and remaining gates.

No sandbox runner/image source, migration, dependency, lockfile, API/UI or evaluation
artifact changed.

## Verification

Python 3.12.14, Node 24.19.0 and Docker Desktop Linux ARM64. Used dedicated Compose
project `runveil-phase10e`, loopback port 55432, with explicit local-only database
settings. Integration fixtures created/migrated/dropped their random test databases.
Other projects and prior evidence volumes were left untouched. Reviewed image:

```text
sha256:1b4e847dba90e9aac1cb869e9df43fe4561b9eddb79aca3b582c60a608711349
```

| Command                                                                                                                                 | Result                                                                                        |
| --------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| `uv run ruff format --check .`                                                                                                          | Passed                                                                                        |
| `uv run ruff check .`                                                                                                                   | Passed                                                                                        |
| `uv run mypy`                                                                                                                           | 132 source files passed                                                                       |
| `uv run pytest -m 'not integration'`                                                                                                    | 153 passed                                                                                    |
| `RUNVEIL_SANDBOX_IMAGE="$SANDBOX_IMAGE" uv run pytest packages/persistence/tests/test_software_worker.py -x`                            | 7 passed                                                                                      |
| `RUNVEIL_SANDBOX_IMAGE="$SANDBOX_IMAGE" uv run pytest -m integration -q`                                                                | 197 passed; all five real-Docker tests enabled                                                |
| `uv run alembic upgrade head` / `uv run alembic check`                                                                                  | Passed; no schema drift                                                                       |
| `docker build --network=none -t runveil-sandbox:phase10e sandbox`                                                                       | Passed; unchanged runner/fixtures                                                             |
| `uv run python scripts/phase10_sandbox_acceptance.py --image "$SANDBOX_IMAGE" --output docs/operations/evidence/phase10e/boundary.json` | Isolation, failing baseline, watchdog, output limit and cancellation passed                   |
| `uv run python scripts/phase5_acceptance.py`                                                                                            | Real SIGKILL checkpoint recovery, uncertain intent, live-lease deferral and duplicates passed |
| `npm run format:check`                                                                                                                  | Passed                                                                                        |
| `npm run lint` / `npm run typecheck`                                                                                                    | Passed                                                                                        |
| `npm test`                                                                                                                              | 11 tests passed                                                                               |
| `npm run build`                                                                                                                         | Passed                                                                                        |
| `uv run python scripts/smoke.py`                                                                                                        | API/web health, production pages/protections and database readiness passed                    |
| `git diff --check`                                                                                                                      | Passed                                                                                        |

The new Docker integration case starts fresh CLI processes for submit, inspect,
work, approve/reject and final inspection. It verifies recorded baseline failure
before proposal generation, exact approved diff, passing post-change tests,
profile isolation, no mutation on rejection, terminal duplicates, trace accounting
and absence of all owned containers. Deterministic boundary tests separately cover
WRITE refusal, reuse of the inspection checkpoint and no adapter/replay after
uncertain baseline or mutation effects. Existing Phase 10D tests continue to cover
full workspace/preimage refusals, failed validation, fences, drift and cleanup.

A separate retained CLI acceptance ran against the local verification database,
with independent exact replacement and expected postimage-digest assertions:

- Approved run: `e15ce50a-54b6-4b64-b824-ec8624f8e0d5` — baseline failed,
  exact patch approved/applied, post-change tests passed, terminal SUCCEEDED.
- Rejected run: `05fba75d-d17b-4dc0-b4a6-9c1c675a6a8c` — baseline failed,
  exact proposal rejected, no mutation, terminal FAILED.

[Workflow evidence](evidence/phase10e/workflow.json) retains identities, decisions,
ordered tool records, exact diff, original and post-change test output and cleanup.
[Boundary evidence](evidence/phase10e/boundary.json) retains the isolation probes.
The service is stopped after verification; the retained runs remain in
`runveil-phase10e_postgres_data`. No owned sandbox containers remain.

## Limits and next review

This is one scripted public task, not general model quality, hostile multi-tenant
isolation or full Phase 10 acceptance. No paid/hosted provider or remote service was
used. Docker verification ran locally on ARM64; CI's Linux environment was not
remotely executed. Existing daemon/image/shared-kernel trust, crash-cleanup duties,
admission-versus-revocation limits and test-output trust remain unchanged.

Covered implementation changes intentionally invalidate older live bindings. Use
an unchanged installation for clean continuation of old runs; do not bypass identity
checks. Unknown-intent terminal recovery remains binding-free. No automatic repair
retry, rollback, second mutation or surviving workspace is introduced.

Recommended next slice: review 10E, then deliberately add several pinned project-owned
fixture tasks with independent acceptance and audit bounded sandbox search and the
remaining charter requirements before claiming Phase 10 closure. Stop here for review.
