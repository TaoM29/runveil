# Phase 11C handoff: acceptance and closure review

Date: 2026-10-02. Closure assessed; human review pending. No commit or push.

## Findings and change

Reviewed the original Phase 11 charter, architecture, ADRs 0040/0041, completed
adapter and pinned worker against discovery, schema mapping, invocation, grants,
durability, recovery, telemetry and approval isolation. The
[closure audit](PHASE_11.md) records evidence and limits for every requirement.

Found one concrete acceptance gap: `EvalCase.expected_tools` accepted only the two
repository tool names, despite the scorer already consuming transport-neutral
native records. Reproduced rejection of `mcp.fixture.info` in the existing real
MCP worker integration test, then changed the oracle to the shared validated
`Name` contract. The same test now verifies pass, wrong-tool mismatch and preserved
model/tool/token/cost accounting through the unchanged scorer. The existing
untrusted-mutation evaluation case now expects that mutation and still proves
zero tool calls: oracle content cannot grant authority.

No new test cases, dependencies, migrations, dispatch paths, permissions, server
profiles or transport support. Frozen suite digests still pass. Evaluator source
fingerprints change normally; comparisons still require identical implementation
fingerprints. No new architectural decision supersedes the accepted MCP ADRs.

## Files

Created:

- `docs/operations/PHASE_11.md`: original acceptance/checklist and boundary audit.
- `docs/operations/PHASE_11C.md`: this handoff.

Modified:

- `packages/evaluations/src/runveil_evaluations/contracts.py`: validated generic oracle tool names.
- `packages/persistence/tests/test_mcp_worker.py`: existing real MCP run scored by native evaluator.
- `packages/persistence/tests/test_evaluations.py`: expected name still cannot authorize mutation.
- `ARCHITECTURE.md`, `ROADMAP.md`: closure assessment and human review gate.
- `docs/operations/MCP.md`, `docs/operations/EVALUATIONS.md`: closure links and oracle/authority distinction.

## Verification

Used native Python 3.12.14 via
`UV_PROJECT_ENVIRONMENT=/tmp/runveil-phase11-venv` and Node 24.19.0 with
`/Users/taom/.nvm/versions/node/v24.19.0/bin` prepended to `PATH`. The dedicated
Compose project `runveil-phase11-review` used explicit `POSTGRES_USER=runveil`,
`POSTGRES_DB=runveil`, `POSTGRES_PASSWORD=runveil-local-only`, `POSTGRES_PORT=55413`.
`DATABASE_URL` selected its `runveil` database and
`RUNVEIL_TEST_DATABASE_URL` its `postgres` administration database on loopback.
No existing database was reset.

Commands and results:

- `uv run pytest packages/persistence/tests/test_mcp_worker.py -k grant_identity -q --tb=short`:
  before the fix, failed exactly at the repository-only oracle restriction.
- `uv sync --locked --all-packages`: passed; lockfile unchanged.
- `uv run ruff format --check .`: passed, 282 files.
- `uv run ruff check .`: passed.
- `uv run mypy`: passed, 148 source files.
- `uv run pytest -q --tb=short`: 376 passed, 11 Docker-opt-in cases skipped.
  Includes all 20 MCP adapter/persistence/worker cases, evaluation, frozen corpus,
  authorization, approval and telemetry regression checks.
- `uv run alembic upgrade head` and `uv run alembic check`: passed; no new operations.
- `uv run python scripts/phase5_acceptance.py`: both real SIGKILL cases,
  active-lease deferral, duplicate acknowledgement and temporary database cleanup passed.
- `npm run lint`, `npm run typecheck`, `npm test`, `npm run build`: passed;
  13 frontend tests in six files.
- `npm run format:check` and `git diff --check`: passed.
- `uv run python scripts/smoke.py`: API/web health, showcase/operator routes,
  framing/referrer protections and database readiness passed.

Additional Docker regression commands:

```sh
docker build --network=none -t runveil-sandbox:phase11-review sandbox
RUNVEIL_REVIEW_IMAGE=$(docker image inspect runveil-sandbox:phase11-review --format '{{.Id}}')
uv run python scripts/phase10_sandbox_acceptance.py --image "$RUNVEIL_REVIEW_IMAGE" --output /tmp/runveil-phase11-review-sandbox.json
RUNVEIL_SANDBOX_IMAGE="$RUNVEIL_REVIEW_IMAGE" uv run pytest packages/persistence/tests/test_sandbox_worker.py packages/persistence/tests/test_sandbox_review.py packages/persistence/tests/test_sandbox_patch_worker.py packages/persistence/tests/test_software_worker.py -k real_docker -q --tb=short
```

Image build and sandbox boundary acceptance passed. The Docker integration run
was incomplete: five passed, two failed, five setup/teardown errors, 39 deselected.
The failures coincided with PostgreSQL connection refusal and Docker storage I/O
errors; the host reported only 138 MiB available. Docker then reported its database
container stopped and could not read container logs or image metadata due to I/O
errors. This is not a passing Docker regression result. No unrelated files,
volumes or images were deleted to recover space. The earlier complete 11-case
Docker result in [Phase 11B](PHASE_11B.md) is historical evidence only.

Cleanup was attempted only for this review's Compose project and image tag.
Compose stopped the database but could not remove its container because Docker's
metadata database returned an I/O error. Image-tag removal was refused because
container `c59f0acfd448` still referenced it. The disposable project/volume, image
tag and interrupted sandbox container may remain; remove these review resources
after restoring Docker health. No cleanup success is claimed.

## Storage recovery and focused rerun

Follow-up on 2026-10-02: restored Docker metadata writes by clearing reproducible
host caches and restarting Docker Desktop. Removed Runveil's generated
`apps/web/.next/cache`; `uv cache prune` removed 336 KiB of dangling cache entries;
`python3 -m pip cache purge` removed 2,692 cached downloads (2,818.5 MB). The native
verification environment has no pip, so the purge used the system Python command.
Installed packages, source files and unrelated database volumes were preserved.
Docker restart briefly interrupted other local containers; their running services
returned afterward. No global Docker prune or data reset was used.

After restart, removed the previously stranded sandbox container `c59f0acfd448`,
then successfully ran the dedicated Compose `down --volumes` and removed only the
`runveil-sandbox:phase11-review` tag. Recreated the same isolated project/port and
rebuilt the sandbox from unchanged source for the focused rerun.

The rerun uses the same Python environment and administration URL as above:

```sh
uv run pytest packages/tool_runtime/tests/test_mcp.py packages/persistence/tests/test_mcp_execution.py packages/persistence/tests/test_mcp_worker.py -q --tb=short
```

All 20 MCP cases passed, including fresh-process recovery, no unsafe replay,
permissions, native evaluation scoring and telemetry. The sandbox image build and
`phase10_sandbox_acceptance.py` command above were repeated with output at
`/tmp/runveil-phase11-review-recheck.json`: passed isolation, expected failed
baseline, watchdog, output limit and cancellation. All four recorded outcomes
have `cleanup_confirmed=true`; cancellation cleanup is also confirmed.

The exact Docker integration command above then passed: **11 passed, 39 deselected**
in 106.48 seconds. The original interrupted run remains recorded for diagnosis;
this successful rerun closes its verification gap. No Runveil defect was exposed
and no implementation or test source changed during the follow-up.

Before teardown, a query of the dedicated PostgreSQL instance found no remaining
`runveil_test_*` databases, and Docker listed no containers with the
`runveil.sandbox=docker-fixture-v1` label. Final cleanup succeeded:

```sh
POSTGRES_USER=runveil POSTGRES_DB=runveil POSTGRES_PASSWORD=runveil-local-only POSTGRES_PORT=55413 docker compose -p runveil-phase11-review down --volumes
docker image rm runveil-sandbox:phase11-review
```

Subsequent label-filtered container, volume and network listings for this Compose
project were empty. The sandbox container listing and review image-tag listing
were also empty. Thus neither the interrupted nor rerun review resources remain.
Host free space remained above 2 GiB; disk pressure is relieved but capacity is
still limited. No unrelated Docker resources were removed.

Only MCP tests, the interrupted Docker regression/boundary acceptance, cleanup
checks and documentation formatting/diff checks were rerun. The earlier full
Python/frontend/migration/smoke results above were not repeated. This follow-up
updates only this handoff, the closure audit and roadmap status.

## Remaining concerns and next slice

The trusted-host, decoded-size, installation-stability and admission-not-revocation
limits in the audit remain. No external MCP service, hosted model, AWS, MCP-specific
SIGKILL harness or new interactive browser verification was used. The standard
suite exercised fresh-process MCP recovery and uncertain-effect refusal using
real local SDK servers. Docker regression does not establish MCP isolation.

The Docker verification and cleanup gap is resolved. Recommend human acceptance
of Phase 11 within the existing trusted local read-only scope. After acceptance
and explicit continuation authorization, plan the smallest Phase 12 infrastructure
slice. Stop here; no commit, push or automatic continuation.
