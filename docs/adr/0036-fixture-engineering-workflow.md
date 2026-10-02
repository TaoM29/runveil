# ADR 0036: Durable fixture engineering workflow

- Status: Accepted for Phase 10E
- Date: 2026-10-02

## Decision

Add configuration/checkpoint version 15 and a separate `software-engineering-v1`
profile. Connect the existing clamp capabilities into one ordered run: inspect the
pinned fixture, execute baseline tests, propose an exact replacement, pause for
human approval, then apply and validate with explicit operator WRITE/EXECUTE.
Reuse the version-14 mutation boundary and disposable runner unchanged. Existing
profiles retain their contracts; the new profile does not adopt their approvals.

A proposal requires one completed failing baseline (exit 1), following inspection
and preceding the proposal model request. Core checks the ordered tool context;
persistence independently checks recorded invocation order, model provenance and
matching observations at pause, decision and mutation admission. Baseline timeout,
output limit or unexpected passing tests terminate with retained evidence, without
proposal or mutation. A model cannot finish this workflow before approved validation.

Expose all phases, including pre-approval failures and unknown mutation outcomes,
through local inspection. Keep approval and execution grants separate, immutable
image/fixture/implementation/endpoint binding, resource bounds, durable intent,
cleanup confirmation and conservative no-replay recovery.

## Scope and trade-offs

The current request prioritizes connecting existing capabilities. Retain the single
project-owned clamp task rather than expanding the fixture catalog concurrently.
The scripted provider demonstrates orchestration, not general repair capability or
model quality. Search, several independent coding tasks and the Phase 10 closure
audit remain future review gates. No arbitrary repository, command, host mutation,
provider service, automatic approval, iterative repair, migration or dependency.
