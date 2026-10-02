# ADR 0042: Private AWS data foundation before application deployment

- Status: Accepted for Phase 12A implementation; review pending
- Date: 2026-10-02

## Context

The charter targets AWS with Terraform but permits smaller coherent slices and
refinement of its example architecture. Phase 11 has closure evidence; the current
user explicitly authorizes Phase 12 without implying historical human sign-off.

The runtime is not a generic cloud worker service. PostgreSQL owns leases, recovery,
approvals and history. The SQS adapter accepts only `fixture-calls-v1`, with one-shot
relay/consumer commands. The API's approval and trace tokens serve a local operator,
not a public control plane. Repository/MCP profiles pin local identities; sandbox
profiles require a trusted Docker daemon. Fargate does not expose a host container
runtime or support privileged containers, so those workers cannot simply be moved
into a Fargate task. See [AWS's Fargate security boundary](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/fargate-security-considerations.html).

## Decision

Implement two small Terraform roots, with logical files rather than reusable module
layers: a state bootstrap and an environment data foundation. Pin Terraform and the
AWS provider, commit both dependency locks, and run credential-free provider-mocked
tests in CI. No cloud apply is part of this implementation.

Each environment has a separate state bucket and an explicitly selected account and
region. Production must use a separate AWS account; resource names and tags alone
are not an isolation boundary. Provider account allowlists prevent accidental
cross-account operations. Use the default workspace only, S3 native state locking,
versioning, encryption, blocked public access and TLS-only bucket access. Bootstrap
state is first local, then migrated into its own bucket under a distinct key. Keep
state lifecycle separate from environment teardown; prevent bucket destruction.

The environment creates a VPC with two isolated database subnets, no Internet/NAT
route and a closed default security group. API, worker and migration client groups
have only reciprocal TCP 5432 access to the database group. They are unattached
interfaces for subsequent compute, not deployed applications. No public ingress,
VPN, bastion, peering, endpoints or generic Internet egress is added.

RDS uses PostgreSQL 17, matching Compose, with an explicit regional minor version,
encrypted 20 GiB gp3 storage, TLS enforcement, automated backups, final snapshots,
and deletion protection. RDS manages the administrator secret; Terraform never
reads its value. Runtime database users, grants and secret injection require a
separate migration/deployment slice. Applications must not receive the administrator
secret. Non-production is single-AZ; production is Multi-AZ with 14 days of backups.
Storage autoscaling and automatic minor upgrades are disabled to keep cost and
version changes reviewed. Operators must monitor capacity and schedule supported
minor upgrades; a fixed storage cap is not an availability guarantee.

SQS remains a Standard notification queue with server-side encryption and TLS-only
access. Its 1024-byte limit, 10-second long poll and 30-second visibility match the
adapter. Neither visibility nor DLQ delivery replaces database ownership. Use a
four-day source retention and fourteen-day DLQ retention, restricted redrive source,
and 100 receives before redrive. This conservative count accommodates healthy
660-second claims and intentionally deferred messages better than a small poison
threshold. It is still not a proof that a DLQ message is malformed. Recurring outbox
publication may produce fresh notifications for the same run after redrive. Investigate
the durable run before manual redrive; no automated replay is authorized.

Separate, initially unattached IAM policies allow relay send and consumer
receive/delete only on this environment's source queue. No API queue authority,
DLQ administration, secret reads, wildcard allow or new trusted principal is created.
Attach these policies only to reviewed identities in the compute slice. Provisioning
permissions necessarily exceed runtime permissions and must not be reused by tasks.

A CloudWatch DLQ alarm records an inspectable condition with no notification action.
This is not an operational paging system. No RDS statement logs are exported: the
current database stores sensitive run content, and logging policy needs a separate
review. Native service metrics remain available. No artifact S3 bucket, ECR, ECS,
load balancer, GPU, custom KMS key or application secret shell exists without a
current consumer. S3 here is for Terraform state only.

## Consequences and acceptance limits

This slice can provision the private data boundary, not a usable cloud application.
Phase 12 remains open until image/compute, runtime database privileges, secret
injection, private migration access, TLS/API exposure, worker supervision, alerts,
live health/recovery and teardown acceptance are demonstrated. The next slice should
package and supervise the API and fixed SQS fixture path with separate task roles;
keep Docker-dependent profiles out until their execution boundary is reviewed.

Offline plans/tests establish Terraform expression, schema and policy boundaries.
They cannot establish AWS regional availability, IAM enforcement, quotas, restore,
cost, network reachability, RDS migrations or live SQS delivery. Live acceptance must
use a reviewed non-production account and cost estimate. Deletion protection and
retained snapshots intentionally require explicit operator steps. See the
[AWS runbook](../operations/AWS.md).
