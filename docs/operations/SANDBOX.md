# Disposable fixture sandbox — Phase 10A

The Phase 10A standalone command is a local **operator-only boundary demonstration**.
The Phase 10B durable worker integration is described below; neither completes the
software engineering application. Use a reviewed image built from the
`sandbox/` directory. A Linux Docker daemon with cgroup v2, CPU/memory/PID controls
and default seccomp is required; Docker Desktop's Linux VM is supported. Docker,
the image and the local operator are trusted. Do not expose this command publicly.

## Build and run

From the repository root:

```sh
uv sync --locked --all-packages
docker build --network=none -t runveil-sandbox:phase10a sandbox
SANDBOX_IMAGE=$(docker image inspect runveil-sandbox:phase10a --format '{{.Id}}')
uv run python -m runveil_tools.sandbox --image "$SANDBOX_IMAGE" --fixture boundary-v1
uv run python -m runveil_tools.sandbox --image "$SANDBOX_IMAGE" --fixture clamp-v1
uv run python scripts/phase10_sandbox_acceptance.py --image "$SANDBOX_IMAGE" --output /tmp/runveil-sandbox-acceptance.json
```

Build may download the digest-pinned Python base image; execution uses `--pull=never`.
No package installation or network is needed inside the container. Only the sandbox
build context is sent to Docker; project credentials and checkouts are not mounted.
The runner selects `/var/run/docker.sock` explicitly and ignores inherited Docker
endpoint/context/TLS/API settings. For another local daemon socket, pass `--socket`
to both runner/acceptance commands and build against that same daemon explicitly.
Remote endpoints are not supported. Image tags are refused by the runner.

`clamp-v1` is an intentionally buggy baseline: it should return `tests_failed` and
CLI exit 1, with the lower-bound assertion visible in bounded JSON output. That is
expected acceptance, not a successfully solved task. `boundary-v1` should pass.
`timeout-v1` sleeps past the eight-second in-container watchdog; `output-v1` floods
stdout until the host capture limit stops it. These last three are infrastructure
probes, not benchmark cases. No correct clamp patch is supplied to model context.

The acceptance command refuses to overwrite an existing output file. It verifies
all four classifications and cancellation of an actual running container, checking
that no new labeled containers remain. Do not run it concurrently with another
sandbox acceptance batch. Its report records image/policy/fixture identities,
output hashes/excerpts and cleanup results. The retained [local evidence](evidence/phase10a/sandbox.json)
is adapter evidence, not a persisted runtime run or a Phase 8/9 evaluation report.

## Boundary and result meanings

- Fixed command and closed fixture IDs; no model command, arguments, source path,
  environment, mounts, network request, test discovery root or image selection.
  Image and daemon are selected by the operator only.
- UID/GID 65532, no capabilities, no-new-privileges, default Docker seccomp, no
  network, read-only root, no host/daemon mounts, no IPC sharing or persistent logs.
- CPU quota 0.5, memory 128 MiB with no additional swap, 32 PIDs, 64 descriptors,
  no core dumps. Writable tmpfs: workspace 16 MiB and temp 8 MiB, noexec/nosuid/nodev.
  Python can interpret files on noexec storage; this flag does not forbid source execution.
- Fixed project fixture copied from image into a new tmpfs repository. No workspace
  export or host mutation. Tests receive only PATH, HOME and LANG.
- Eight-second container test watchdog, 15-second host command/attach deadlines,
  16 KiB combined raw output cap. Decoding invalid UTF-8 may expand returned text;
  JSON escapes control characters. All test output is untrusted content.
- Exit 0 → `passed`; exit 1 → `tests_failed`; watchdog exit 124 or host attach
  deadline → `timeout`; overflow → `output_limit`; other exits, OOM and Docker
  failures → `infrastructure_error`. A test exit alone is not proof of correctness.
- Force removal and absence check run on success, failure and cancellation. Each
  cleanup command has its own 15-second bound; cancellation waits for cleanup.
  No automatic retries, retained workspace, resume or tool replay.

CLI exit 0 means passed; 1 means a completed non-pass result; 2 means invalid local
configuration, unavailable Docker, or unconfirmed cleanup. Cancellation normally
exits 130. Control-command diagnostics are not returned as result payloads.

## Uncertain cleanup and limitations

`sandbox_cleanup_unconfirmed:runveil-sandbox-<id>` identifies only the runner-owned
container. This includes an uncertain create, even when an immediate query sees no
container: a daemon request may complete after the client timeout. After Docker is
healthy, inspect/remove **that exact name** and verify absence. Following a host
crash, list owned containers before choosing individual names for removal:

```sh
docker ps -a --filter label=runveil.sandbox=docker-fixture-v1
# Replace the example with the exact name from the diagnostic/listing.
docker rm --force --volumes runveil-sandbox-EXACT-ID
```

Do not bulk-remove other tasks' containers. A stopped container can remain after
SIGKILL or daemon outage; no durable cleanup reconciler is claimed. The in-container
watchdog protects the supported fixture subprocess, not arbitrary hostile images.
The Docker daemon grants substantial host authority and containers share a kernel.
This is not a hardened public or multi-tenant execution service.

Existing runtime EXECUTE denial, durable intent/recovery, approval and WRITE grants,
trace projections and evaluation guards are unchanged. Next work must define a
pinned durable execution profile before making sandbox execution agent-accessible.
See [ADR 0032](../adr/0032-disposable-fixture-sandbox.md).

## Durable sandbox tests — Phase 10B

`runveil_worker.sandbox_worker` adds one offline `sandbox-tests-v1` profile for the
fixed `clamp-v1` baseline. It exposes only `tests.run` with empty arguments through
a narrow core execution path. The ordinary tool registry remains read-only. The
image, fixture, isolation policy, local socket identity and covered implementation
are pinned in configuration version 12. No WRITE/NETWORK permission, repository
mount, patch, approval substitution or persistent workspace is enabled.

After building the image above and migrating the local database:

```sh
# DATABASE_URL must name the migrated local Runveil database.
SANDBOX_IMAGE=$(docker image inspect runveil-sandbox:phase10a --format '{{.Id}}')
uv run python -m runveil_worker.sandbox_worker submit --image "$SANDBOX_IMAGE"
# Copy the returned UUID into RUN_ID.
RUN_ID=RETURNED-UUID
uv run python -m runveil_worker.sandbox_worker work --run-id "$RUN_ID" --image "$SANDBOX_IMAGE" --allow-execute
```

Submission pins authority but does not execute Docker. Work additionally requires
an explicit operator EXECUTE grant. Both calls accept `--socket` for the same local
absolute Unix socket. Socket path/device/inode and adapter/core source fingerprints
must still match. Daemon restart, source changes or a different image can refuse
clean execution. Keep the pinned image locally available: rebuilding a tag can
remove its previous local image ID. Hashes identify the binding, not its authenticity or the entire
host environment. The reviewed image and trusted daemon assumptions still apply.

The profile permits two scripted model calls, one tool call and three steps; it
pins a 120-second elapsed budget plus the existing token/cost/repeated-call limits.
Usage/pricing remain synthetic. Tests are never retried. A test failure is recorded
as a successful tool observation with `status: tests_failed`, followed by final
summary `Sandbox test status: tests_failed.` and run status SUCCEEDED. This means
the observation workflow completed; it does **not** mean the code was repaired.
Infrastructure/cleanup failures instead produce a failed tool and FAILED run.

The tool result holds at most 4096 characters of untrusted output with an explicit
truncation flag. Existing trace API/UI show invocation identity/status, budgets
and final summary; raw tool output remains in the durable tool record/context.
Opt-in telemetry works through the existing `RUNVEIL_TELEMETRY=json` setting.
No new API/UI or evaluation suite is introduced. Historical evidence is unchanged;
source changes correctly change existing implementation fingerprints.

### Recovery and ownership

Every attempt commits a tool intent before Docker work. Its container name is
`runveil-sandbox-` followed by the tool-call UUID **without hyphens**. Ownership,
revision/history and elapsed budget are rechecked before create and before start.
Outcome writes remain fenced. Docker I/O does not hold database locks. A request
already sent, or a process paused immediately after admission, cannot be atomically
revoked by PostgreSQL; container limits still apply and stale outcomes cannot commit.

Clean checkpoints resume under the identical binding and explicit EXECUTE grant,
without repeating committed results. After a crash leaves an unresolved model/tool
intent, the same work command can terminate it without Docker, image, socket access
or an execution grant:

```sh
uv run python -m runveil_worker.sandbox_worker work --run-id "$RUN_ID"
```

It still respects the existing 660-second live lease; it never steals ownership.
Once eligible, the worker validates the fixed profile/history and records
`execution_interrupted` (or elapsed expiry when that takes precedence). It never
replays the uncertain call, inspects Docker to guess its outcome, or adopts a
container. Terminal duplicates select no work. Configuration/grant rejection may
leave the acquired lease until expiry, matching existing worker admission behavior.
Do not manually shorten production leases to bypass an active owner.

Operator container cleanup remains separate. Inspect the exact derived name after
a crash or failed invocation before concluding its resources are gone. Budget or
ownership failures can take precedence over cleanup errors; only a committed result
with `cleanup_confirmed: true` confirms successful observed cleanup. An absent name
immediately after an uncertain create is not proof that a delayed daemon request
cannot create it later. No cleanup reconciler or exactly-once guarantee is added.

### Verification

The normal integration suite uses PostgreSQL and deterministic Docker-command stubs
for grants, image drift, persisted provenance, recovery cuts, stale ownership,
model argument refusal and safe cleanup failures. Real Docker is separately opt-in:

```sh
export RUNVEIL_TEST_DATABASE_URL='postgresql+psycopg://runveil:runveil-local-only@127.0.0.1:5432/postgres'
RUNVEIL_SANDBOX_IMAGE="$SANDBOX_IMAGE" uv run pytest packages/persistence/tests/test_sandbox_worker.py -k real_docker
```

That test executes a fresh worker process, verifies the real failed baseline against
its persisted tool record and checks container removal. CI runs it after building
the sandbox image and the Phase 10A isolation acceptance. See
[ADR 0033](../adr/0033-durable-sandbox-execution.md) and [handoff](PHASE_10B.md).

## Sandbox inspection and exact review — Phase 10C

`sandbox-review-v1` is a separate offline worker, with configuration/checkpoint
version 13. Its first tool call runs the fixed `repository.inspect` operation
inside a disposable container from the pinned image. It reads only TASK.md,
clamp.py and test_clamp.py, at most 4096 UTF-8 bytes each and 12000 serialized
bytes overall. Files must be ordinary, contain no NUL, and match the complete
ordered allowlist. The runner does not import fixture code during inspection.
Malformed, failed, truncated or oversized output cannot become a preimage.

The scripted provider proposes one exact clamp.py replacement. Core validation
and the database pause/decision boundaries independently compare its before-text
to the successful recorded inspection preceding the proposal model request.
A clean restart uses that record without another container. An uncertain
inspection or proposal intent fails without constructing an adapter or replaying
Docker. The existing name/cleanup/operator recovery procedure above still applies.

Build the current reviewed image before submitting; do not move its tag during
an active acceptance run. Export the migrated `DATABASE_URL` as in development:

```sh
docker build --network=none -t runveil-sandbox:phase10c sandbox
SANDBOX_IMAGE=$(docker image inspect runveil-sandbox:phase10c --format '{{.Id}}')
uv run python -m runveil_worker.sandbox_review_worker submit --image "$SANDBOX_IMAGE"
# Set RUN_ID to the returned UUID.
uv run python -m runveil_worker.sandbox_review_worker work --run-id "$RUN_ID" --image "$SANDBOX_IMAGE" --allow-execute
uv run python -m runveil_worker.sandbox_review_worker inspect --run-id "$RUN_ID"
# Use the inspected revision and approval.digest, after reviewing exact before/after and diff.
uv run python -m runveil_worker.sandbox_review_worker approve --run-id "$RUN_ID" --revision "$REVISION" --digest "$DIGEST"
uv run python -m runveil_worker.sandbox_review_worker work --run-id "$RUN_ID" --image "$SANDBOX_IMAGE" --allow-execute
```

Use `reject` with the same revision/digest arguments to terminate instead. Decisions
are one-time and do not dispatch workers. The local CLI is a trusted database
operator interface; the existing approval HTTP API/browser console do not support
this new profile. The read-only trace API supports version 13 accounting and
approval metadata, while continuing to omit raw file/proposal payloads.

Inspection output includes exact proposal text, its digest, immutable sandbox
identity, an inspection digest, before/after SHA-256 hashes and a deterministic
unified diff. JSON escapes terminal controls; exact before/after text is canonical,
including final newlines. The diff is a display aid, not an executable patch.
Approval resumes only to a persisted review summary: **no patch is applied**.
This profile has neither WRITE nor NETWORK permission. Existing version-11 host
patch authority cannot adopt these approvals.

The worker pins five steps (three model calls, two tool calls), a one-hour elapsed
budget, and the existing token/cost/repeated-call budgets; no retry is allowed.
Review wait consumes the original deadline. The explicit `--allow-execute` grants
the two fixed capabilities (inspection EXECUTE and proposal READ), including on
clean continuation. Changed image, socket identity or covered implementation
refuses execution. Admission refusal may retain the normal lease until expiry.
Terminal uncertain-intent recovery needs only `work --run-id`, as for Phase 10B.

CI runs the real fresh-process review test alongside the durable test worker:

```sh
RUNVEIL_SANDBOX_IMAGE="$SANDBOX_IMAGE" uv run pytest packages/persistence/tests/test_sandbox_worker.py packages/persistence/tests/test_sandbox_review.py -k real_docker
```

Applying patches, testing repaired results and demonstrating several controlled
tasks remain later Phase 10 work. This scripted repair proposal establishes no
model-quality claim. See [ADR 0034](../adr/0034-sandbox-inspection-review.md) and
[handoff](PHASE_10C.md).

## Approved sandbox patch and validation — Phase 10D

`sandbox-patch-v1` is a **new** fixed worker profile, configuration/checkpoint
version 14. Create a new run for this workflow: Phase 10C review-only approvals
cannot authorize mutation. The profile inspects the three clamp fixture files and
pauses with the exact proposal. Its approval explicitly permits applying that
replacement and running the fixed tests inside a fresh disposable sandbox.

```sh
docker build --network=none -t runveil-sandbox:phase10d sandbox
SANDBOX_IMAGE=$(docker image inspect runveil-sandbox:phase10d --format '{{.Id}}')
uv run python -m runveil_worker.sandbox_patch_worker submit --image "$SANDBOX_IMAGE"
# Set RUN_ID to the returned UUID.
uv run python -m runveil_worker.sandbox_patch_worker work --run-id "$RUN_ID" --image "$SANDBOX_IMAGE" --allow-execute
uv run python -m runveil_worker.sandbox_patch_worker inspect --run-id "$RUN_ID"
# Review the exact proposal, identity, revision, approval.digest and application consequence.
uv run python -m runveil_worker.sandbox_patch_worker approve --run-id "$RUN_ID" --revision "$REVISION" --digest "$DIGEST"
uv run python -m runveil_worker.sandbox_patch_worker work --run-id "$RUN_ID" --image "$SANDBOX_IMAGE" --allow-execute --allow-write
uv run python -m runveil_worker.sandbox_patch_worker inspect --run-id "$RUN_ID"
```

`reject` uses the same revision/digest arguments and terminates without mutation.
Approval alone dispatches nothing. Both explicit EXECUTE and WRITE grants are
required for the approved continuation. The general registry and model offers do
not expose apply_patch. Host patch, fixture/SQS, review-only and sandbox-test
workers cannot adopt this profile. The trusted local database operator CLI is its
interface; the existing approval HTTP API/browser console remains unchanged.

Before mutation, the worker revalidates the pinned image, socket and implementation.
Persistence rechecks the approved proposal and original inspection/model provenance,
then commits one `repository.apply_patch` intent. Its existing unique index prevents
a second mutation. Final database fences recheck exact intent, approval, grants,
lease/history and deadline before create and start. Docker I/O occurs outside
transactions; admission checks cannot revoke an already-sent request.

Only bounded JSON goes through stdin. No host mounts, arbitrary commands, environment
or model-selected paths are accepted. The container reconstructs the pinned fixture,
requires the exact three-entry workspace and all recorded file bytes, and compares
the clamp.py preimage before atomic replacement. The proposed after-text is limited
to 4096 UTF-8 bytes; the complete input is limited to 32768 bytes, with an
eight-second input watchdog if the host disappears. Fixed unittest
arguments run in a separate process with an eight-second watchdog and 2048-byte
combined output limit. Its process group is stopped before all fixture bytes and
directory entries are checked again. Unexpected changes make the outcome uncertain.
Container resources and verified removal remain as documented above.

The mutation result retains `applied`, proposal/before/after workspace digests,
`approved_diff`, bounded test output/status, and confirmed cleanup. Exact approved
text is the patch artifact; no checkout or modified container is retained. A known
application with failed tests, timeout or excess test output is a successful tool
observation but a FAILED run (`sandbox_validation_failed`), so its evidence remains
inspectable. A preimage refusal records `tool_resource_invalid` and no application.

`inspect` reports `patch_applied: null` for an uncertain mutation. An unresolved
mutation intent, invalid/missing result, infrastructure/cleanup failure, postimage
drift or deadline crossing during a possible mutation cannot prove its outcome.
Recovery records `sandbox_patch_outcome_unknown`, with no adapter construction,
Docker access, rollback or replay. For expired-lease terminal recovery:

```sh
uv run python -m runveil_worker.sandbox_patch_worker work --run-id "$RUN_ID"
```

An owned container name is still derived from the mutation UUID. Use the existing
operator cleanup procedure after crashes; no automatic reconciler or exactly-once
claim is introduced. Completed terminal duplicates do not dispatch or rebind.
Review waiting consumes the original one-hour deadline; this profile permits two
model calls and three tool calls (five total steps), with existing token/cost limits.
Tests execute proposed code only inside the container. Pass/fail and output are
observations, not a proof against malicious code. Trusted-image/daemon and shared
kernel limits remain; this is one scripted controlled repair, not multi-task coding
acceptance or evidence of model quality.

CI opts into the new fresh-process patch test and real preimage/validation boundary
exercise with the same image used for the existing sandbox checks. See
[ADR 0035](../adr/0035-approved-sandbox-patches.md) and [handoff](PHASE_10D.md).
