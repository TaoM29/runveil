# ADR 0010: Explicit repository disclosure and bounded native reads

- Status: Accepted for Phase 4B
- Date: 2026-09-27

## Decision

Add `runveil_tools` in `packages/tool_runtime` for filesystem access and native
repository contracts/handlers. Depend on core; core does not import the adapter.
Expose only `repository.read_file` and `repository.search`, through Phase 4A's
registry, READ/READ_ONLY classification, intersected grants, deadlines and durable
request/outcome path. No shell, Git subprocess, directory discovery or mutations.

The operator binds a local root and an explicit allowlist of at most 128 canonical
relative POSIX file paths. Empty means no file access. Reject absolute paths,
traversal, empty/dot components, backslashes, colons, control characters and hidden
components (including `.git` and `.env`), even in operator configuration. No globs,
automatic tracked-file trust, extension-based secret detection or gitignore parser.
The operator must select content safe to disclose to a model and durable history;
an allowlisted ordinary source file may still contain secrets or prompt injection.

Open the operator-selected root once (resolving its trusted path at binding time),
then use descriptor-relative opens with O_NOFOLLOW for every component. Intermediate
components must be directories; the final descriptor must be a regular file on the
root device with one hard link. Reject special files without blocking on FIFOs.
Never resolve a model path and then reopen it by absolute pathname. Root replacement
cannot redirect a binding. Each operation owns duplicated descriptors, all closed
on success/failure. Support POSIX platforms with these primitives (macOS/Linux);
fail closed elsewhere.

Read at most 64 KiB plus one overflow-detection byte per file; reject larger files,
invalid UTF-8, NUL text and files that change metadata while being read. Reads use
character offsets and at most 4096 returned characters, with an explicit next offset.
Search is case-sensitive literal substring matching, one match per line, in sorted
allowlist/line order. Scan at most 1 MiB per call, return at most 10 bounded excerpts,
and report truncation when an additional match exists. Failure reading any visited
allowlisted file or exceeding the scan budget fails the call, without partial
results or silently implying that all files were searched. Output worst-case JSON
escaping remains within the existing 64 KiB tool limit.

## Async, errors and limitations

Offload bounded filesystem work to a thread so local reads do not block the event
loop. Cancellation/timeouts stop waiting, not an already running system call; an
in-flight read may finish and close its own descriptors after the binding closes.
A lock guards root duplication/close, preventing descriptor reuse races. Use trusted
local filesystems; hard deadlines on hung mounts require process isolation later.

Extend the safe error vocabulary for unavailable resources, resource limits and
invalid text. Preserve only the enum code of deliberate ToolError exceptions from
native handlers, normalizing all other exceptions as before. No paths, OS exception
messages or file bytes enter failure payloads. Authorization denial precedes I/O.

These are live reads, not a revision-pinned repository snapshot. Different calls
may observe edits. Metadata checks detect ordinary concurrent changes, not a
malicious local writer. Concurrent directory moves, mounts, privileged writers and
hard-link manipulation are outside this boundary; use an operator-controlled
checkout. The root/allowlist binding is operator configuration, not persisted
executable state. Durable replay needs a workspace identity/revision policy in a
later slice. No claim of containment against arbitrary native Python is made.
