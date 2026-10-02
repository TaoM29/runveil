# Phase 10A handoff — disposable fixture sandbox

Implemented 2026-10-02 from clean `8513b83`; ready for review. The user authorized
Phase 10 continuation after Phase 9. No commit or push was made.

## Implementation and decisions

Inspected Phase 9's completed statistical implementation, acceptance evidence,
current roadmap, charter and relevant architecture/ADRs. The planned next coherent
slice is the sandbox boundary, before granting agents execution capability.

Added an operator-only Docker runner with immutable local image selection, closed
fixture IDs, fixed test invocation, resource and output limits, disposable tmpfs
storage, bounded subprocess transport and cleanup on every lifecycle path. Added
one intentionally failing clamp fixture and three infrastructure probes. Local
JSON preserves bounded failure evidence and identities. CI now builds the reviewed
fixture image and runs real Docker acceptance.

[ADR 0032](../adr/0032-disposable-fixture-sandbox.md) records the boundary and limits.
No runtime registry permission was widened; no persistence, approval, mutation,
trace, telemetry, provider or scoring logic changed. No new package, dependency or
migration. New adapter source naturally changes the existing evaluator's whole-
package implementation fingerprint; historical reports remain unchanged and cannot
be compared across different fingerprints.

## Files created

- `packages/tool_runtime/src/runveil_tools/sandbox.py`: runner and operator CLI.
- `packages/tool_runtime/tests/test_sandbox.py`: four behavioral tests (nine collected
  cases) for closed input, flags, safe failure/cleanup, uncertain creation, repeated
  cancellation, real subprocess output bounds and deadlines.
- `sandbox/Dockerfile`, `sandbox/.dockerignore`, `sandbox/runner.py`: digest-pinned
  image, narrow context and container-only watchdog/test entrypoint.
- `sandbox/fixtures/clamp-v1/{TASK.md,clamp.py,test_clamp.py}`: failing coding baseline.
- `sandbox/fixtures/boundary-v1/test_boundary.py`: actual isolation/resource checks.
- `sandbox/fixtures/timeout-v1/test_timeout.py`: watchdog probe.
- `sandbox/fixtures/output-v1/test_output.py`: output-limit probe.
- `scripts/phase10_sandbox_acceptance.py`: real-container acceptance command.
- `docs/adr/0032-disposable-fixture-sandbox.md`: architectural decision.
- `docs/operations/SANDBOX.md`: usage, classifications, limits and recovery.
- `docs/operations/evidence/phase10a/sandbox.json`: final real Docker evidence.
- `docs/operations/PHASE_10A.md`: this handoff.

## Files modified

- `.github/workflows/ci.yml`: image build and sandbox acceptance.
- `pyproject.toml`: include the container entrypoint in strict mypy checks.
- `README.md`, `ARCHITECTURE.md`, `ROADMAP.md`: implemented scope and next gate.
- `docs/operations/DEVELOPMENT.md`: sandbox verification reference/prerequisites.

## Verification

Local Python 3.12; Node 24.19.0 explicitly selected from nvm. Docker Desktop
28.5.2, Linux ARM64, cgroup v2, default seccomp. The real-container acceptance
passed twice, including after conservative uncertain-create handling was added.
Retained evidence is from the final runner. The image ID is in every record.

Commands executed from the repository root:

```sh
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest -m 'not integration'
uv run pytest packages/tool_runtime/tests/test_sandbox.py

docker build --network=none -t runveil-sandbox:phase10a sandbox
SANDBOX_IMAGE=$(docker image inspect runveil-sandbox:phase10a --format '{{.Id}}')
uv run python -m runveil_tools.sandbox --image "$SANDBOX_IMAGE" --fixture boundary-v1
uv run python scripts/phase10_sandbox_acceptance.py --image "$SANDBOX_IMAGE" --output /tmp/runveil-phase10a-final.json

export POSTGRES_USER=runveil POSTGRES_DB=runveil
export POSTGRES_PASSWORD=runveil-local-only POSTGRES_PORT=55432
docker compose -p runveil-phase10a up -d --wait --wait-timeout 90
export DATABASE_URL='postgresql+psycopg://runveil:runveil-local-only@127.0.0.1:55432/runveil'
export RUNVEIL_TEST_DATABASE_URL='postgresql+psycopg://runveil:runveil-local-only@127.0.0.1:55432/postgres'
uv run alembic upgrade head
uv run alembic check
uv run pytest -m integration
uv run python scripts/phase5_acceptance.py

npm run format:check
npm run lint
npm run typecheck
npm test
npm run build
uv run python scripts/smoke.py
git diff --check
```

Formatting/lint/strict typing pass. The full non-integration batch passed 150 cases;
the final targeted sandbox batch adds the uncertain-create case for nine sandbox
passes. No application change followed that full batch. Frontend lint/typecheck,
11 tests and production build passed. Real API/web smoke passed with both missing
and configured database readiness. All 158 PostgreSQL integration tests passed;
Alembic upgraded the fresh database and reported no model/migration drift. The
Phase 5 SIGKILL acceptance passed both checkpoint recovery to success and uncertain
intent failure without replay, including active-lease deferral and duplicate
acknowledgement. Its disposable database was removed.

Docker acceptance verifies actual UID/GID, capabilities, seccomp/no-new-privileges,
read-only root, writable workspace, disabled external networking, absent daemon
socket, controlled environment and cgroup CPU/memory/PID limits. It also verifies
baseline failure output, watchdog exit 124, exact 16 KiB output truncation and
cancellation cleanup. No sandbox containers remain after acceptance.

Initial database attempts using quickstart defaults failed authentication. Compose
had selected a different local user/database, including for the first disposable
instance. Explicitly setting all four POSTGRES variables fixed the dedicated test
instance. Existing credentials and data were not changed; only this task's newly
created temporary volume was recreated. Initial formatting/type diagnostics were
fixed and the affected checks rerun. Verification containers were stopped afterward;
the dedicated `runveil-phase10a` test volume was removed, while the pre-existing
Runveil volume was preserved. The built fixture image remains available for review.

## Remaining concerns and recommended next slice

This is Phase 10A, not completed Phase 10. No agent solves a coding task yet, and no
EXECUTE permission is granted by this runner. Docker/image/operator are trusted;
this is not a hostile multi-tenant service. SIGKILL/daemon outages can leave stopped
containers; uncertain create always requests operator cleanup even if an immediate
query sees no container. There is no durable cleanup reconciler or restart/resume
contract. Limits and recovery instructions are explicit in SANDBOX.md.

Remote CI was not executed, and the real image was verified on local Linux ARM64,
not independently on CI's AMD64 host. No hosted provider, paid service or AWS test
was run. Existing Phase 9 artifacts and statistical claims are unchanged.

Next: one pinned durable sandbox test-execution profile, with explicit EXECUTE
authorization, committed intent/outcome, ownership fencing and conservative
uncertain-intent recovery. Review this boundary before beginning that slice.
