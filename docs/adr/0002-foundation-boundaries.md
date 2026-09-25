# ADR 0002: Minimal monorepo and initial engineering boundaries

- Status: Accepted
- Date: 2026-09-25

## Context

The charter proposes many packages but also rejects packages containing only
trivial modules. Phase 0 must boot and verify real applications without prematurely
implementing domain behavior.

## Decision

Use a uv workspace with one installable API package and an npm workspace with one
Next.js app. Keep one lockfile per ecosystem. Use Python 3.12, FastAPI/Pydantic,
PostgreSQL, Next.js/TypeScript/Tailwind, Docker, an AWS target and Terraform for
future infrastructure. Use a custom single-agent runtime as recorded in ADR 0001.

Compose runs PostgreSQL only, bound to loopback with persistent local storage.
Apps run natively for development. Health endpoints measure process liveness;
database readiness will be added alongside SQLAlchemy/Alembic in Phase 1.

Create worker, runtime, benchmark and infrastructure directories when they contain
real work. Phase 0 CI verifies the current apps and dependency startup; cloud
credentials, deployments and speculative migration checks are excluded.

## Alternatives

Separate repositories would complicate coordinated API/UI changes. Placeholder
packages and preselected domain interfaces would produce structure without tested
boundaries. Containerizing every process now would increase foundation scope
without demonstrating the runtime's later sandbox requirements.

## Consequences

The tree is intentionally smaller than the target charter example. No runtime
contracts are frozen prematurely. Lockfiles reproduce resolved dependencies;
manifest ranges permit deliberate upgrades. Application container builds,
persistence readiness and infrastructure validation become required when their
implementations arrive. Native platform and CI behavior still need verification.
