# ADR 0034: Durable sandbox inspection and exact review

- Status: Accepted for Phase 10C
- Date: 2026-10-02

## Decision

Add the separate `sandbox-review-v1` profile and configuration/checkpoint version 13. It pins the existing sandbox identity and exposes only a fixed, empty-input
`repository.inspect` EXECUTE operation and `repository.propose_patch` READ
validation. Both pinned and operator grants are required. The general registry
remains read-only; version 11 alone retains approved mutation authority.

Inspection copies the pinned clamp fixture into the existing disposable sandbox
and reads exactly TASK.md, clamp.py and test_clamp.py as bounded UTF-8 ordinary
files, without importing fixture code. No host mount, model-selected path,
command, image, environment or persistent workspace is accepted. The existing
intent-before-I/O, pre-create/pre-start fences, cleanup and uncertain-intent
recovery apply unchanged. Clean recovery uses committed inspection evidence;
it does not inspect again to validate a proposal.

The exact recorded clamp.py preimage is required for a single-file replacement.
Core validates the proposal against its durable context; persistence independently
requires one succeeded inspection preceding the proposal's source model before
creating or resolving an approval. The immutable run/version binds the image and
execution policy; the proposal digest binds exact path/before/after text. Local
inspection exposes that identity, the inspection digest, before/after hashes,
exact proposal and a deterministically derived unified diff. Exact text is the
canonical evidence; the diff is a review aid, not executable patch input.

Reuse the fenced atomic approval pause, lease release, revision/digest decision,
original deadline/accounting and fresh-worker continuation. Approval only permits
finishing review. No patch application, WRITE grant, tests of a repaired task,
search interface, new API/UI capability, migration or dependency is introduced.
The fixed scripted proposal demonstrates integration, not model coding quality.

## Limits

The reviewed image and local Docker daemon remain trusted. This is not a hostile
multi-tenant execution service. Inspection output is untrusted and fails closed
on malformed, incomplete, oversized or failed output; it is never accepted as a
partial preimage. Payloads stay in durable records/local inspection, not telemetry.
The source fingerprint changes with this implementation; older unfinished sandbox
runs may refuse fresh bindings, as designed. Review-only approvals must never be
adopted by a future patch writer. Applying approved patches requires a separately
reviewed profile and recovery contract.

## Subsequent application profile

[ADR 0035](0035-approved-sandbox-patches.md) adds the independent version-14
application profile. It does not upgrade or adopt version-13 review-only approvals.
