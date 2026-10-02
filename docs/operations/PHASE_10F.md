# Phase 10F handoff — controlled multi-task workflow and closure audit

Date: 2026-10-02. Implemented; stop for review. No commit or push.

## Scope and decisions

Inspected the clean repository at `b623e43`, AGENTS.md, charter, architecture,
roadmap, sandbox/approval/workflow ADRs, completed 10E implementation and handoff,
and current development/CI checks. The next coherent slice adds two distinct tasks
to the existing integrated workflow rather than adding a new execution mechanism.

`software-engineering-v1` (version 15) now supports clamp bounds, whitespace slugs
and fractional arithmetic means. Task selection is a closed `--fixture` option at
submission; continuation reloads the immutable sandbox identity and cannot override
it. Existing versions 12–14 remain clamp-only through explicit configuration guards.
The original version-15 clamp enrollment and system prompt remain byte-for-byte
compatible so old uncertain-intent runs can still reach binding-free recovery. New
tasks have their own pinned prompts. No new schema version, migration, permission
or approval capability is required.

Each task has exactly TASK.md, a source file and a test file. Snapshot contracts
accept only a complete ordered entry; adapter, runtime and persistence independently
bind it to the configured task. Proposals target only that task's source. The image
runner independently enforces the selected target and preserves full preimage,
workspace and postimage checks. The catalog joins the covered implementation digest.
The duplicate three-entry mapping inside the standalone image avoids importing host
packages; real inspection/repair acceptance checks that both mappings agree.

The existing baseline/proposal/approval/mutation pipeline, budgets, explicit
operator EXECUTE/WRITE, single-use intent, cleanup and conservative no-replay
recovery remain. The repair provider is still scripted; no model-quality claim is
made. See [ADR 0037](../adr/0037-controlled-task-catalog.md) and
[operator procedure](SANDBOX.md#controlled-task-selection--phase-10f).

## Original Phase 10 assessment

The [closure audit](PHASE_10.md) maps every original implementation requirement
and all three acceptance criteria to evidence. Several tasks now complete end to
end in the bounded scripted scope; failed tasks remain inspectable and fixture
execution stays off the host. **Phase 10 remains open:** bounded search is still
absent from this sandbox workflow. Existing host search and full-file inspection
are not treated as substitutes. No original requirement was waived and Phase 11
was not started.

## Files

Created:

- `packages/agent_core/src/runveil_core/fixtures.py`: three explicit typed task/path entries.
- `sandbox/fixtures/slug-v1/{TASK.md,slug.py,test_slug.py}`: whitespace-normalization task.
- `sandbox/fixtures/mean-v1/{TASK.md,mean.py,test_mean.py}`: fractional/negative-mean task.
- `docs/adr/0037-controlled-task-catalog.md`, `docs/operations/PHASE_10.md`, this handoff,
  and `docs/operations/evidence/phase10f/{tasks,boundary,failed-validation}.json`.

Modified:

- `packages/agent_core/src/runveil_core/{sandbox,sandbox_review,runtime}.py`: closed
  fixture identities, complete snapshot/target binding and legacy profile guard.
- `packages/agent_core/src/runveil_core/software.py`: update the workflow description.
- `packages/tool_runtime/src/runveil_tools/{sandbox,sandbox_execution}.py`: explicit
  task selection, binding checks and catalog implementation pinning.
- `packages/persistence/src/runveil_persistence/worker_approvals.py`: independent
  task-to-inspection validation at existing approval/mutation provenance boundaries.
- `apps/worker/src/runveil_worker/sandbox_patch_worker.py`: submission-only selection,
  pinned continuation and three scripted repairs; reuse existing CLI operations.
- `sandbox/runner.py`: closed task-specific paths for inspection and mutation.
- `packages/agent_core/tests/test_sandbox_review_contracts.py`: one catalog/legacy
  authority test covering forbidden targets and mixed snapshots.
- `packages/persistence/tests/test_software_worker.py`: parameterize existing real
  workflow acceptance across all three tasks; independent exact patch/postimage
  oracle; adapter/core/storage cross-fixture refusals and direct container target checks.
- `README.md`, `ARCHITECTURE.md`, `ROADMAP.md` and
  `docs/operations/{DEVELOPMENT,SANDBOX,WORKER}.md`: current boundaries, operations and gap.

No dependencies, lockfiles, migrations, API/UI or evaluation artifacts changed.
Existing CI already includes the software worker test file and automatically runs
all eight real-Docker cases with the reviewed image.

## Verification and retained evidence

Python 3.12.14, Node 24.19.0; Docker Desktop Linux ARM64. Dedicated local Compose
project `runveil-phase10f` on loopback port 55432, with explicit local-only database
settings. Random test databases are created/migrated/dropped by the existing tests;
other projects and earlier evidence volumes were left alone. Reviewed image:

```text
sha256:bc676fcb9023fcd25156387220f21b93c67bd4f7de0910be12b1b1b2307ed07c
```

| Command                                                                                                                                 | Result                                                                                           |
| --------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| `uv run ruff format --check .` / `uv run ruff check .`                                                                                  | Passed                                                                                           |
| `uv run mypy`                                                                                                                           | 133 source files passed                                                                          |
| `uv run pytest -m 'not integration' -q`                                                                                                 | 154 passed                                                                                       |
| `RUNVEIL_SANDBOX_IMAGE="$SANDBOX_IMAGE" uv run pytest -m integration -q`                                                                | 203 passed; all eight real-Docker cases enabled                                                  |
| `uv run alembic upgrade head` / `uv run alembic check`                                                                                  | Passed; no schema drift                                                                          |
| `docker build --network=none -t runveil-sandbox:phase10f sandbox`                                                                       | Passed                                                                                           |
| `uv run python scripts/phase10_sandbox_acceptance.py --image "$SANDBOX_IMAGE" --output docs/operations/evidence/phase10f/boundary.json` | Passed: isolation, failing baseline, watchdog, output limit and cancellation                     |
| `uv run python scripts/phase5_acceptance.py`                                                                                            | SIGKILL checkpoint recovery, uncertain intent, live-lease deferral and duplicate handling passed |
| `npm run format:check`                                                                                                                  | Passed                                                                                           |
| `npm run lint` / `npm run typecheck` / `npm test` / `npm run build`                                                                     | Passed; 11 frontend tests                                                                        |
| `uv run python scripts/smoke.py`                                                                                                        | API/web health, production pages/protections and readiness passed                                |
| `git diff --check`                                                                                                                      | Passed                                                                                           |

A separate retained acceptance used fresh CLI processes for each submit/work/inspect/
decision/continuation, with independent text, exact patch and full postimage digest
assertions. Fixture Python was never imported or executed on the host.

| Task  | Approved run (SUCCEEDED)               | Rejected run (FAILED, no mutation)     |
| ----- | -------------------------------------- | -------------------------------------- |
| Clamp | `fdb8d537-1d6d-4b4a-8afe-131f4f46fc51` | `31f9f186-c103-41f5-92a5-507176d0243a` |
| Slug  | `6636a61c-6a46-4d29-8d91-20e279d28209` | `48010be2-476f-4fcb-b400-b3bddca42a3a` |
| Mean  | `2b51507b-86bd-4b78-bd31-bbecef348617` | `8ed4de7d-4d2e-48d9-8ad0-4940730535fc` |

[Task evidence](evidence/phase10f/tasks.json) retains fixture/image/implementation
identities, approval decisions, ordered observations, exact proposal/diff and
baseline/post-change test output. All three failing baselines became passing
validation after approved application. Rejection produced no mutation. Duplicate
terminal work did nothing. Tests also verify absence of every owned container.

An additional real-container [failed-validation run](evidence/phase10f/failed-validation.json),
`7d1f31fa-8d47-4cb9-9dc6-6731202b84e3`, explicitly injected an ineffective mean
proposal into the scripted provider. After the trusted test operator approved that
exact proposal, application was confirmed but tests still failed. Inspection retained
`patch_applied: true`, a successful mutation observation and task failure
`sandbox_validation_failed`; duplicate work did nothing. This is labelled fault
injection, not output from the normal repair table.

Development corrections: the independent oracle initially supplied a list to a
strict Python tuple contract; it now parses JSON through the public contract.
The direct runner refusal test initially expected raw exit 125; the adapter
intentionally normalizes unsupported exits to an infrastructure outcome with no
exit code, so the expectation was corrected. No production guarantee was weakened.
The global-container cleanup acceptance initially overlapped other Docker checks;
it was rerun alone with a fresh output file. These are verification corrections,
not reasons to bypass the original boundaries. Final review also caught a prompt
compatibility edge: the old clamp prompt must remain unchanged for fixed-profile
admission before interrupted recovery. That configuration is preserved, an explicit
regression assertion was added, and the Python suites and task evidence were rerun.

## Remaining concerns and next slice

The provider and fixtures are public, scripted integration evidence, not a hidden
benchmark, stochastic evaluation or proof of model quality. Default tests are
observations, not protection against a malicious patch defeating its own tests.
Docker image/daemon trust, shared-kernel limits, admission-not-revocation and manual
crash cleanup remain. No hosted/paid provider was used; remote CI was not executed.

Covered implementation changes intentionally invalidate live bindings from older
installations. Continue those with their original installation or start new runs;
never repin them in place. Unknown-intent terminal recovery still requires no
adapter or fixture replay. Verification data is retained in
`runveil-phase10f_postgres_data`; the service is stopped and owned containers removed.

Recommended next slice: review 10F, then add bounded sandbox-evidence search with
explicit authorization and durable provenance, and reassess the original closure
checklist. Stop here for review; no automatic continuation, commit or push.
