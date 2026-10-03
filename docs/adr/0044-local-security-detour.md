# ADR 0044: Temporary local security track while AWS acceptance is paused

- Status: Accepted for this owner-authorized local implementation; review pending
- Date: 2026-10-03

## Decision

Pause Phase 12C until the owner returns and completes AWS account, billing and
credential setup. Preserve all live gates. Phase 12 is not closed. Temporarily
perform Phase 15A threat analysis, 15B justified local hardening and 15C public-demo
safety policy, in that order, then stop for review. This decision was recorded
before implementation. It supplements the original charter's Phase 15 security
requirements without rewriting the historical charter or changing phase closure.

Keep the custom runtime, immutable configuration, separate operator grants,
durable approval/intent fences and controlled fixture sandbox. Evaluate concrete
attack paths against implemented code; do not introduce a generic security layer,
unrestricted repository execution or new authentication system.

The initial inspection identifies one small implementation gap: core telemetry's
`Observation.fields` forwards arbitrary field names/strings to a supplied tracer,
although the worker JSON exporter filters them. Apply the existing finite metadata
policy before the tracer receives attributes, retaining independent export filtering.
Omit unexpected values rather than attempting regex redaction of arbitrary secrets.
This narrows accidental disclosure at an existing boundary; it does not sanitize
durable model context or constrain trusted custom tracer code.

Add a focused repository-injection regression using the real runtime and durable
store: even a provider that follows hostile file instructions cannot widen tool
authority or disclose files outside the operator selection. Reuse existing path,
sandbox, approval, duplicate-effect, budget and API tests as security evidence.

For 15C, preserve the existing recorded read-only showcase and local operator-only
fixture execution. A policy document is sufficient unless inspection finds a
missing local enforcement boundary. Anonymous execution and public deployment stay
disabled; a speculative public-mode flag or execution endpoint is not needed.

## Consequences and deferred work

No new dependencies, persistence migrations, deployment services or tool grants
are required. Authentication for public administrators, aggregate public rate/cost
limits, cloud IAM/network hardening and live isolation/cleanup acceptance remain
future gates. This local review does not certify hostile multi-tenant isolation.

Resume order: Phase 12C live AWS acceptance, Phase 13 CI/CD, Phase 14 self-hosted
inference, remaining AWS/public-deployment security in Phase 15, then Phase 16
public release. See the [roadmap](../../ROADMAP.md),
[threat model](../security/THREAT_MODEL.md) and
[12C pause record](../operations/PHASE_12C.md).
