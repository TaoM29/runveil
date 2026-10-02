# ADR 0038: Durable search over pinned sandbox evidence

- Status: Accepted for Phase 10G
- Date: 2026-10-02

## Decision

Introduce configuration/checkpoint version 16 and `software-engineering-v2`.
Preserve the version-15 profile/configuration and its CLI for existing jobs.
The new local `software_search_worker` runs inspect → search → baseline tests →
proposal → human approval → approved application and validation. Four model calls
and five tool calls retain the original time/token limits. The v16 cost ceiling is
125,000 nanodollars, allowing four scripted calls (100,000 total) below the strict
budget boundary; v15 retains its original 100,000 ceiling. The scripted provider
uses the search's source return-statement match when selecting its exact repair.

Search the complete immutable snapshot already captured inside the sandbox, not a
host checkout or a newly reconstructed filesystem. This is repository search over
sandbox evidence: a pure bounded computation with no filesystem, subprocess,
network, regex, glob or model-selected path. It needs repository.search and READ
in both pinned and operator policies; inspection/test execution still needs EXECUTE,
and approved mutation still needs separate WRITE. No general registry grant changes.

Accept a case-sensitive literal query of 1–128 characters without CR/LF/NUL and
max_matches 1–10. Scan all three files in inspection order and lines in order,
returning at most one match per line, one-based line numbers, excerpts up to 160
characters, files_scanned=3, truncation and the exact inspection digest. The existing
snapshot limits cap scanned text; the result has no file-access authority.

Persist the ordinary model-directed search intent and outcome. Before accepting
an outcome, persistence recomputes it from the independently recorded inspection
and verifies source-model provenance, context, task binding and event order. At
proposal pause, approval decision and mutation admission, require one successful
search before baseline generation, recompute it, and compare both baseline and
proposal model contexts to the saved result. No forged result or substituted
snapshot can authorize a patch. Existing fences and conservative no-replay recovery
apply even though the search computation itself has no external side effects.

## Scope and closure

Keep the three controlled public fixtures and existing runner unchanged. Add the
search policy to the covered implementation identity. No migration, dependency,
host repository access, API/UI, provider service or repair loop. The query/result
are untrusted model context; normal telemetry does not emit raw text.

This closes the remaining implementation checklist gap within the documented
scripted fixture scope, subject to end-to-end acceptance and human closure review.
It establishes workflow mechanics, not general model repair quality. Search applies
to the saved original snapshot; a later filesystem state is never silently adopted.
