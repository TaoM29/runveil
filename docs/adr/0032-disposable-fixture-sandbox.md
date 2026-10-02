# ADR 0032: Disposable fixture sandbox boundary

- Status: Accepted for Phase 10A
- Date: 2026-10-02

## Decision

Start Phase 10 with an operator-only Docker test runner in the existing tool adapter
package. It executes a closed selection of project-owned fixtures from an explicitly
selected local immutable image ID. There is no shell/command/path argument, host
checkout mount, daemon socket mount, image pull, model call or runtime registration.
The existing registry still denies EXECUTE; approval and WRITE behavior is unchanged.
Agent integration requires a separately reviewed pinned execution profile and durable
intent/recovery design. This slice supplies a concrete boundary for that work.

Use a local Unix Docker endpoint, non-root UID/GID, no network, no capabilities,
no-new-privileges, default seccomp, read-only root, bounded tmpfs workspace and temp
storage, CPU/memory/swap/PID/file-descriptor limits and no Docker log persistence.
Copy the fixed fixture into disposable container tmpfs and execute fixed unittest
arguments. The image has a second, eight-second test-process watchdog; the host bounds
Docker commands and combined attached output. Do not execute fixture Python on the host.
Build context contains only sandbox source; image content identity is reported.

Create before start so cleanup has a known random name. Always force-remove and
query absence, including on timeout, excess output, failed start and cancellation.
Unconfirmed cleanup is an explicit failure with the owned name for operator action.
No retries or reuse. Local JSON contains bounded untrusted output, exit classification,
image, fixture and policy identity; it is not durable runtime/evaluation evidence.

## Limits and trade-offs

Docker and the operator-selected image/daemon are trusted. Containers share a kernel;
this is not a hostile multi-tenant sandbox or public execution service. Docker daemon
access is privileged host authority. Only reviewed images built from this repository
are supported. The immutable image ID pins bytes, not their authenticity.

A dead host runner or unavailable daemon can leave a stopped container; the in-image
watchdog bounds the supported fixture test process but is not independent enforcement
against a hostile image. There is no durable cleanup reconciler or crash-resume claim.
Daemon-side requests may complete after a client timeout; an absence query is evidence
at that instant, not a revocation fence for an uncertain create. Operator cleanup is
required after crashes/daemon outages. Do not attach this runner to durable workers yet.

One intentionally buggy clamp repository provides a real failing baseline; separate
boundary/timeout/output probes exercise containment and cleanup. This is not a solved
coding benchmark. Patching, diff, approval integration, durable EXECUTE authorization,
and end-to-end coding acceptance remain subsequent Phase 10 slices. No migrations,
dependencies or changes to Phase 8/9 artifacts are needed.

Docker flag semantics follow the [run reference](https://docs.docker.com/reference/cli/docker/container/run)
and [resource constraints](https://docs.docker.com/engine/containers/resource_constraints/).

## Subsequent durable integration

[ADR 0033](0033-durable-sandbox-execution.md) adds the explicitly reviewed Phase 10B
worker profile. It supersedes the temporary prohibition on worker integration only
for that pinned, fenced, non-replaying profile; standalone runner and isolation
limits above remain in force.
