# ADR 0021: Durable patch review before mutation

- Status: Accepted for Phase 6A
- Date: 2026-10-01

## Decision

Introduce a bounded, local `patch-review-v1` workflow in the existing core,
persistence and worker packages. It reviews one UTF-8 single-file replacement
proposal (relative path, exact before/after text), not arbitrary patch syntax.
A SHA-256 digest binds the complete canonical proposal. No filesystem is read or
written; text is supplied by the caller and is not proof of workspace contents.

One immutable request per run and a one-time approve/reject outcome live in a new
approval table. Request/event/checkpoint/pause commit together. Resolution locks
the run, requires the inspected lifecycle revision and proposal digest, records a
decision event, and either fails the run on rejection or resumes it to checkpoint
an approved review result and succeeds. Success means review completed only.
There is no mutation capability or reusable execution authorization in this slice.
A repeated or competing decision fails closed rather than silently changing it.
Cancellation invalidates resolution; pending requests on cancelled runs remain
inspectable and cannot authorize anything. Transactions are caller-owned.

This deliberately separate workflow cannot attach to worker-enrolled runs or
arbitrary runtime configurations. Existing worker claims, retries, budgets,
checkpoint recovery and mutation denial stay unchanged. Existing runtime checkpoint
schemas cannot safely consume approval event tails without explicit integration;
we do not disguise this workflow as a supported durable worker profile.

The local CLI and database credentials are the trusted operator boundary, as in
admission repair. It exposes an offline fixed proposal demonstration plus inspection
and resolution across process restarts. No identity/authentication claim is made.
Do not store secrets in proposal text. Events carry only request ID and digest;
the proposal is retained once in the approval record. Input text/paths are bounded
and validated; it is untrusted review data, never code or shell instructions.

## Scope and trade-offs

This is Phase 6's approval persistence and lifecycle foundation, not completion of
Phase 6. Integrating model-proposed mutations, workspace/preimage identity, a
controlled writer, uncertain-effect recovery, authenticated HTTP endpoints and UI
requires subsequent review. Keeping writes disabled makes this first boundary
reviewable without weakening Phase 5 guarantees. A later writer must recheck
policy, exact request, current workspace and single-use execution state; an approved
review here must not automatically become permission to apply a patch.

Database constraints/triggers preserve request identity and one-time outcomes.
As elsewhere, trusted repositories own atomic semantic writes; privileged SQL is
not an authorization boundary. Downgrade discards approval records and is not an
operational way to resolve a waiting run.
