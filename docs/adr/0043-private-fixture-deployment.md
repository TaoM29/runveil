# ADR 0043: Private API and fixed-fixture Fargate deployment

- Status: Accepted for Phase 12B implementation; review pending
- Date: 2026-10-02

## Decision

Extend the existing environment root behind `enable_private_runtime=false` by
default. No reusable module or new Python package is needed. One immutable backend
image supports a private API, separate SQS relay and consumer services, and an
explicit one-shot migration task. Only `fixture-calls-v1` is executable through
this deployment. There is no web service, hosted model, Docker daemon, MCP server,
repository mount or agent-configurable command.

Use Fargate Linux AMD64 at 0.25 vCPU/512 MiB per task. Services start at zero replicas.
Activation requires a digest-pinned image and operator attestation that the migration
task for that exact digest succeeded. Every service independently checks migration
revision `0010` before starting. Terraform never runs SQL or fetches secret values.
This is a manual release gate, not automated proof of migration completion; the
operator must inspect the task's container exit code and success marker.

## Data and identities

Separate ECS task roles and execution roles for API, worker, relay and migration.
Only the worker task role receives the existing consumer policy; only the relay task
role receives send authority. API and migration task roles have no AWS policies.
Execution roles can pull this environment's ECR image, write their own retained log
streams, and inject only their own secrets. ECR authorization-token retrieval requires
`Resource: *`; repository reads remain scoped. No runtime role can read Terraform
state, change infrastructure, fetch secrets through the SDK, administer SQS, or
assume the migration identity. The privileged operator's `RunTask`/`PassRole` powers
must be restricted outside this root; no CI deployment identity is introduced.

RDS's managed administrator credential is injected only into the one-shot migration
task. That task upgrades the schema and checks metadata inside an explicit transaction,
serializes with a transaction advisory lock, and creates/reconciles three unprivileged
login roles. PostgreSQL superuser authority is not required: the migration owner needs
database ownership and CREATEROLE/admin authority over the runtime roles. Existing
elevated attributes or memberships are rejected, not silently adopted.

The API reads only the tables used by trace projection and the schema marker.
The consumer reads required runtime tables, updates runs/jobs/invocations, and appends
history/admission evidence; it cannot enroll new work, publish outbox state, delete
history, change schema or disable triggers. The relay reads runs/jobs/outbox and updates
only outbox lease/publication columns. Trigger functions retain invoker semantics.
No application receives ownership or schema CREATE. These are table-level service
boundaries, not tenant isolation or row-level confinement; this environment must
contain only the reviewed fixed-fixture deployment.

Three independent 64-hex-character passwords and an API-access JSON secret are
provisioned into Terraform-owned Secrets Manager containers outside Terraform state.
There are no `secret_version` resources. Secret population and rotation are explicit
operator operations. The migration task can also be deliberately overridden to the
fixed `submit` command to enroll a fixture for acceptance; submission does not call
AWS or expose an HTTP write surface. This is an administrative task, not worker authority.

## Networking and API

Two new application subnets keep the database subnets and their route table isolated.
No Internet/NAT route or public task address. ECR API/DKR, Logs, Secrets Manager and
SQS use interface endpoints; ECR layers use a restricted S3 gateway endpoint. No ECS
endpoint is needed for Fargate's control plane. Endpoint traffic is HTTPS from explicit
client groups, with IAM and endpoint policies restricting callers. Non-production
uses one endpoint AZ; production uses two. This accepts non-production AZ dependency
and possible cross-AZ charges in return for lower fixed endpoint cost.

The API serves TLS on 8443 only to an unattached operator-client security group.
It exposes liveness, readiness and bearer-authenticated read-only traces, reusing the
existing projection. It does not register approvals, submission, OpenAPI or docs routes.
Operator-provided certificate/key material is injected into a mode-0600 ephemeral
volume. No ALB, Cloud Map, public DNS, VPN or bastion is provisioned just to provide
an operator path. Operators with existing private access discover the task IP and
connect using their approved certificate hostname. The bearer remains a single
installation-wide operator credential, not public or multi-tenant authentication.

Database clients use the real RDS hostname with `sslmode=verify-full` and a vendored
public AWS root bundle. The internal API health probe trusts the exact installed
certificate chain, permits that leaf as an anchor, and omits hostname verification
only for its same-container loopback connection. External acceptance verifies both
CA trust and hostname from a separate client. Certificate renewal requires a reviewed
image/secret update as appropriate and a service restart.

## Process, cost and recovery

The image pins Python and uv base manifests, installs locked non-editable production
dependencies and runs as UID/GID 65532 with a read-only root, dropped capabilities
and one writable ephemeral `/tmp` volume. The Docker daemon is not available inside.
One image avoids duplicated build/dependency tooling; entry points, network, database
and AWS privileges bound its three service modes. The worker dependency graph still
contains trusted adapter libraries; their presence does not grant execution authority.

Relay/consumer supervision reuses the existing one-shot functions without changing
claims, retry classification, terminal acknowledgements or outbox consistency. Every
iteration waits at least one second; errors back off to 30 seconds and emit a fixed
message without raw exceptions. SIGTERM stops new work and allows 80 seconds to drain,
then cancels cooperative work, leaving room for the bounded SDK thread before ECS's
120-second stop timeout. Forced death can leave a lease or unresolved intent, handled
by the existing conservative recovery protocol. No uncertain external action is replayed.

Each service has one desired task and no deployment surge. Deployment and certificate
rotation can interrupt API availability; this is a cost-bounded private acceptance
setup, not high availability. No autoscaling, Container Insights, NAT, ALB, GPU or
collector. Logs retain seven days in non-production and thirty in production; access
logs and raw application exceptions are suppressed. Worker process existence is not
queue health: stalled-progress metrics/alerts and paging remain a later operations gate.

## Verification and limits

Terraform tests cover default-off costs, private task definitions, identity/secret
separation, endpoint boundaries and release activation. Real PostgreSQL tests exercise
migration as a non-superuser owner, repeated migration, queue publication/execution,
terminal duplicates, trace reads and denied crossed privileges. A disposable image
smoke uses TLS PostgreSQL, a separate TLS API client and signal-driven worker stops on
an internal Docker network with no AWS access. CI builds and runs this acceptance.

No live apply, ECR push, AWS IAM denial, endpoint delivery, RDS migration/restore,
cloud certificate/DNS access or ECS rollout is claimed. Regional service availability,
account quotas, live pricing, operator access and recovery remain explicit acceptance
gates in the [runtime runbook](../operations/AWS_RUNTIME.md). Phase 12 remains open.

Sources: [ECR private endpoints](https://docs.aws.amazon.com/AmazonECR/latest/userguide/vpc-endpoints.html),
[Fargate networking](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/fargate-task-networking.html),
[ECS secret injection](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/secrets-envvar-secrets-manager.html).
