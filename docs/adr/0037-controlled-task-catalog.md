# ADR 0037: Closed multi-task sandbox workflow

- Status: Accepted for Phase 10F
- Date: 2026-10-02

## Decision

Extend the version-15 software workflow with an explicit three-task allowlist:
clamp bounds, whitespace slugs and fractional means. Pin the selected fixture in
SandboxIdentity at submission; work and recovery derive it from that immutable
configuration. Do not accept fixture overrides during continuation. Versions 12–14
remain clamp-only, including their configuration validators. Preserve the original
version-15 clamp task and system prompt exactly so legacy uncertain-intent recovery
can still pass fixed-configuration admission; new tasks get their own pinned prompts.

Each fixture has exactly TASK.md, one source file and one test file. Accept only a
complete ordered snapshot from one catalog entry; core, adapter and persistence
independently bind that entry to the configured fixture. A proposal may replace
only that entry's source file. The image runner has its own closed mapping and
revalidates every file and directory entry before/after the existing atomic
replacement and fixed tests. Image, endpoint and implementation pinning remain;
the implementation digest includes the catalog.

Keep the current ordered workflow, approval digest/revision, separate operator
WRITE/EXECUTE grants, single-use mutation, bounded resources/output, cleanup,
durability and conservative no-replay recovery. No new schema version is needed:
fixture identity already exists, and no execution or approval capability changes.
Old installations' live bindings must not be silently repinned after code changes.

## Scope and evidence

Use distinct public fixture bugs and a closed scripted repair table. Real Docker
acceptance verifies each failing baseline and approved repair in fresh worker
processes, with independent expected replacements and unchanged task/test files.
The fixtures are integration demonstrations, not holdouts or model-quality evidence.
Do not execute/import their code on the host.

Assess the original Phase 10 checklist separately. This slice does not silently
count complete-file inspection as search: bounded sandbox search remains absent.
Several-task acceptance can be evidenced without declaring all Phase 10 work closed.
No arbitrary repositories, paths, commands, provider calls, dependencies, migrations,
API/UI expansion, generic task registry or repair loop.
