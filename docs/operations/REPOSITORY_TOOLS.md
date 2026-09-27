# Repository read/search tools

Phase 4B supplies two native tools through `runveil_tools.repository`. They run
through the same typed registry, grants, deadlines and persisted outcome path as
the fixture. No shell, Git command, directory traversal/discovery or mutations are
exposed. Use a trusted local checkout on macOS/Linux.

## Binding and disclosure

The operator selects the root and exact files. Both agent-version and operator tool
grants must still allow the tool names and READ permission. Keep the binding alive
until `execute` returns, using a context manager:

```python
from pathlib import Path

from runveil_core.tools import Permission, ToolPolicy, ToolRegistry
from runveil_tools.repository import RepositoryAccess, RepositoryTools

policy = ToolPolicy(
    allowed_tools=("repository.read_file", "repository.search"),
    permissions=(Permission.READ,),
)
# Persist tool_policy=policy in the run's version-2 RuntimeConfig first.
with RepositoryTools(
    Path("/operator/selected/checkout"),
    access=RepositoryAccess(files=("src/service.py", "tests/test_service.py")),
) as repository:
    state = await execute(
        run.id,
        "Inspect the service and its tests.",
        provider_name="scripted",
        provider=provider,
        store=store,
        tools=ToolRegistry(repository.bindings()),
        tool_policy=policy,
    )
```

Root and allowlist are operator-side configuration, not model arguments. The model
cannot extend them. The allowlist defaults to empty; up to 128 exact paths are
accepted, sorted and deduplicated. Do not generate it automatically from every
tracked file. Hidden path components (including `.git`, `.env` and hidden
configuration folders) are refused even if explicitly listed. Paths must be
canonical relative POSIX names, at most 256 characters, without traversal, empty
components, backslashes, colons or control characters. File contents are not
secret-scanned: vet selected content before exposing it to the provider and history.
Gitignore status and file extensions are not authorization.

A root descriptor anchors the lifetime of the binding. Every component is opened
relative to a held directory descriptor without following symlinks. Files must be
regular, on the root device, and have only one hard link. Missing files, links,
unreadable/special files and ordinary changes detected during a read fail safely.
Replacing the root pathname does not redirect an existing binding. Absolute root
paths and OS error text are not included in results or failures.

## Contracts and bounds

- `repository.read_file`: `{ "path": "src/service.py", "offset": 0, "max_chars": 4096 }`.
  Returns `path`, `content`, and `next_offset` (null at EOF). Offsets count decoded
  Unicode characters, not bytes or lines. `max_chars` is 1–4096; the default is 4096.
  Offset beyond EOF is invalid. An empty file returns empty content and null.
- `repository.search`: `{ "query": "literal substring", "max_matches": 10 }`.
  Query is 1–256 characters, without CR/LF/NUL. Matching is case-sensitive and
  literal, with one result per matching line in sorted path/line order. Results
  include relative `path`, one-based `line`, and an excerpt of at most 160 characters
  around the first occurrence. Excerpts can clip long queries/lines. Output contains
  `matches`, `files_scanned`, and `truncated`; truncation means an additional match
  was found beyond the requested limit (1–10). There is no search continuation cursor.
- Each visited file must be at most 64 KiB and valid UTF-8 without NUL. This whole-file
  limit applies even to a short requested excerpt. Reads detect overflow with at
  most one extra byte. No binary decoding fallback or replacement characters.
- Search reads at most 1 MiB of accepted file content per call, plus at most one
  overflow-detection byte. Exceeding that budget or failing any visited file fails
  the whole call, with no partial results. Early match truncation can leave later
  files unvisited; `files_scanned` and `truncated` make that boundary explicit.
- Defaults retain the typed binding's 10-second cooperative deadline and no retries.
  Returned character/path/match bounds fit the registry's 64 KiB JSON output limit,
  including worst-case escaping. Results are labelled untrusted tool observations
  in model context and persisted with the original request identity/provenance.

Safe failures are `invalid_tool_arguments` for malformed paths/inputs or offsets
beyond EOF, `tool_permission_denied` for files outside the allowlist, and
`tool_resource_unavailable`, `tool_resource_limit`, or `tool_resource_invalid`
for inaccessible/changed resources, size/scan bounds, or invalid text. Generic
unexpected native errors remain `tool_failed`. Errors expose fixed codes only.
Each tool failure atomically records a failed outcome/checkpoint and fails the run.

## Lifetime and limitations

Filesystem work runs in a thread. Async cancellation/deadlines stop waiting;
already-running reads can finish after cancellation or binding close. Each owns
and closes its descriptors; queued work after close cannot reopen the root.
A hung filesystem syscall cannot be forcibly cancelled, so use local trusted
filesystems. This is not a process sandbox or protection against hostile native
code, privileged writers, mount changes, concurrent directory relocation or
hard-link manipulation. File metadata checks catch ordinary edits but do not
establish a cryptographically immutable snapshot. Different calls may see edits.

The root/allowlist and repository revision are not durably pinned. Interrupted runs
still cannot resume; a later recovery design must establish workspace and tool
implementation identity before replay. No worker, retry, approval or MCP work is
included here.

Run `uv run python scripts/runtime_demo.py` against a migrated local database for
an offline model → search → model → read → model finish demonstration. It uses a
temporary public fixture directory, not the developer's checkout, deletes that
directory after execution, and retains one new agent/version/run in PostgreSQL.
