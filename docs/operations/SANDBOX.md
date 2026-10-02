# Disposable fixture sandbox — Phase 10A

This is a local **operator-only boundary demonstration**, not an agent tool or a
completed software engineering application. Use a reviewed image built from the
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
