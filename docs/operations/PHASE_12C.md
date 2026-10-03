# Phase 12C: live AWS acceptance preflight

Date: 2026-10-02. **Paused by the owner on 2026-10-03 until their return and
completion of AWS account, billing and credential setup. Phase 12 remains open.**
No AWS resources have been provisioned or deleted during this attempt. No Git
commit or push was performed. This record is not live acceptance evidence.

## Inspected baseline

The working tree was clean at
`d79a2b920dda4e5353364eb21cac582c7fb63849` (`feat: add private AWS API and worker deployment`).
Reviewed `AGENTS.md`, the charter, architecture, Phase 12 roadmap, ADRs 0042/0043,
the AWS foundation/runtime runbooks, development guidance and existing Terraform
and container configuration. Phase 12B's local evidence remains in its
[handoff](PHASE_12B.md); it is not substituted for live AWS verification.

The intended acceptance uses the existing non-production private RDS/SQS/Fargate
model, explicit migration task, separate runtime identities and digest-pinned image.
No architecture or application behavior was changed during preflight.

## Evidence collected

- `git status --short`: clean at entry.
- Neither `aws` nor `terraform` is on the shell PATH. The existing standalone
  `/tmp/runveil-terraform/terraform version` reports **1.13.5, darwin_arm64**.
- `terraform fmt -check -recursive infra/terraform` using that binary: passed.
- No `AWS_*` environment variables were set; `~/.aws/config` and
  `~/.aws/credentials` were absent. No operator `.tfvars`, `.tfbackend`,
  `.tfstate` or `backend_override.tf` files were present under `infra/terraform`.
- The existing Python SDK, with instance-metadata lookup disabled, reported
  `available_profiles=[]`, `region_name=None` and no resolved credentials.
  Credential values were not printed. No STS identity or AWS inventory could be verified.
- Docker's bounded health check returned `OK`; about 4.3 GiB was free locally.
- The Phase 12B local image exists as
  `sha256:088429fec6fd2d82f069b067060409b6a5f621871030493fba25ff581302a08c`.
  This is a local image ID, not an ECR deployment digest or a new build result.

## Required inputs and continuation

Requested the non-production account/profile, region and acceptance spending limit,
with short-lived authentication established locally rather than secret keys sent in
chat. Also requested whether an existing private operator client is available or
a temporary in-VPC acceptance task is needed. Example account IDs and regions in
the runbooks are not a selected target.

Once supplied, verify STS account identity, existing environment/state ownership,
regional PostgreSQL/class availability, quotas, budget/alert configuration and cost.
Review saved plans before provisioning. Follow [AWS operations](AWS.md) and
[private runtime operations](AWS_RUNTIME.md) for image publication, external secret
population, explicit migrations and staged activation. Collect actual task exit
codes, TLS/API responses, fixture completion and crossed-authority denials.

Teardown must account for the protected state bucket, final snapshot, retained
automated backups and seven-day secret recovery windows. Inventory and report every
retained resource and its disposition; an environment destroy alone does not prove
zero residual resources or cost. No teardown claim is possible before provisioning.

All requested live gates remain unperformed: provisioning, migrations, private API
health, queue/worker execution, database connectivity, runtime boundary enforcement
and cleanup. Continue this acceptance slice when access and target details are
available and the owner returns; do not add services to work around missing credentials.
Teardown and retained-resource cleanup are pending acceptance gates, not completed
actions. While paused, only the explicitly authorized local Phase 15A–15C security
detour proceeds. The [roadmap](../../ROADMAP.md#intended-resume-order) records the
resume order; no Phase 12 closure or live AWS evidence is implied.
