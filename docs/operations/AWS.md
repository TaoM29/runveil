# AWS infrastructure: Phase 12A

The default configuration is the private data foundation. [Phase 12B](AWS_RUNTIME.md)
adds opt-in private runtime deployment and supersedes the deferred-compute notes below.
The implementation
has not been applied to AWS. Full Phase 12 health and teardown acceptance is open.
See [ADR 0042](../adr/0042-private-aws-data-foundation.md) and the
[handoff](PHASE_12A.md).

## Reproducible offline checks

Install Terraform **1.13.5** from HashiCorp and verify its published checksum. The
AWS provider is pinned to **6.16.0**, with signed registry checksums in both locks.
Upgrades require a reviewed lock update and the checks below. No AWS credentials
or backend access are needed; every test file explicitly mocks the AWS provider.

When creating or updating provider locks, include both the Linux CI platform and
the native Mac development platform for each root:

```sh
for root in bootstrap environment; do
  terraform -chdir="infra/terraform/$root" providers lock -platform=linux_amd64 -platform=darwin_arm64
done
```

Commit the resulting locks. The platform-specific `h1` hashes are required for
validation of the unpacked provider when CI uses `-lockfile=readonly`; archive
`zh` hashes alone do not cover that validation step on a different platform.

```sh
terraform fmt -check -recursive infra/terraform
for root in bootstrap environment; do
  terraform -chdir="infra/terraform/$root" init -backend=false -input=false -lockfile=readonly
  terraform -chdir="infra/terraform/$root" validate
  terraform -chdir="infra/terraform/$root" test
done
uv run pytest packages/persistence/tests/test_configuration.py
```

CI runs these Terraform checks separately from application checks. Environment
mock tests exercise private network rules, encrypted data, TLS, protected deletion,
production settings, queue redrive and least-privilege policies. Bootstrap uses a
mocked plan so `prevent_destroy` remains intact. Mock apply means simulated resources,
not AWS provisioning; it cannot replace a real plan or live acceptance.

## Environment and state workflow

Use short-lived AWS SSO/assumed-role credentials. Never put credentials in backend
configuration, tfvars, CLI arguments, source or build logs. Use a separate production
account, and a dedicated bucket and working directory per environment. Do not use
Terraform workspaces. Account guards on both the provider and S3 backend must name
the same approved account. Keep bootstrap and environment state under different keys.
Backend selection is operator-controlled: Terraform cannot prove that a manually
supplied backend bucket matches the provider variables. Review both before each plan.

The following is a workflow template, not permission to provision. Substitute the
approved account/region; confirm two standard AZs and a currently offered RDS
PostgreSQL 17 minor version using AWS's regional engine-version and orderable-instance
APIs. The pinned `db.t4g.micro` class must support that version, gp3 and the chosen
region. The Terraform provider accepts configuration that the regional service may
reject. Keep one foundation per environment per account (IAM policy names are global); do not rename it in
place or mix states in the same initialized directory.

Create an ignored `bootstrap.tfvars` in `infra/terraform/bootstrap`:

```hcl
account_id  = "123456789012" # Replace this example account.
region      = "eu-west-1"
environment = "dev"
```

Review cost and provisioning-role permissions, then bootstrap deliberately:

```sh
terraform -chdir=infra/terraform/bootstrap init -input=false -lockfile=readonly
terraform -chdir=infra/terraform/bootstrap plan -var-file=bootstrap.tfvars -out=bootstrap.tfplan
terraform -chdir=infra/terraform/bootstrap apply bootstrap.tfplan
```

The bucket name is `runveil-ACCOUNT-REGION-ENV-state`. It blocks public access and
ACLs, requires TLS, encrypts with SSE-S3, retains object versions, and refuses forced
or normal Terraform destruction. Bootstrap initially uses local state. Protect that
file and its backups; after bucket creation create an **ignored** `backend_override.tf`
in the bootstrap directory with this exact backend block:

```hcl
terraform {
  backend "s3" {
    bucket              = "runveil-123456789012-eu-west-1-dev-state"
    key                 = "bootstrap/terraform.tfstate"
    region              = "eu-west-1"
    allowed_account_ids = ["123456789012"]
    encrypt             = true
    use_lockfile        = true
  }
}
```

Run `terraform -chdir=infra/terraform/bootstrap init -migrate-state`, confirm the
migration, and verify `terraform state list` from that root before removing protected
local copies. Retain a secured backup until recovery is verified. Do not create this
override during offline tests. Bootstrap never destroys its own state bucket.

Create ignored `environment.tfvars` in `infra/terraform/environment` with the same
account, region and environment plus:

```hcl
availability_zones = ["eu-west-1a", "eu-west-1b"]
postgres_version   = "17.9" # Example only: confirm regional availability first.
vpc_cidr           = "10.42.0.0/16" # Choose a non-overlapping network.
```

Create ignored `environment.tfbackend` there:

```hcl
bucket              = "runveil-123456789012-eu-west-1-dev-state"
region              = "eu-west-1"
allowed_account_ids = ["123456789012"]
```

The environment root fixes `foundation/terraform.tfstate`, encryption and native
S3 lockfiles. Initialize, review the full plan and apply only the saved plan:

```sh
terraform -chdir=infra/terraform/environment init -reconfigure -backend-config=environment.tfbackend -lockfile=readonly
terraform -chdir=infra/terraform/environment plan -var-file=environment.tfvars -out=environment.tfplan
terraform -chdir=infra/terraform/environment apply environment.tfplan
```

State and plans are sensitive even without plaintext RDS passwords. Do not publish
`terraform show -json`, state or saved plans as CI artifacts. Ignore rules cover state,
plans, operator variables and backend configuration. Never use `-target` for ordinary
provisioning or teardown. Never force-unlock without confirming the lock owner is gone.

Following [HashiCorp's S3 backend permissions](https://developer.hashicorp.com/terraform/language/backend/s3),
grant the state operator `s3:ListBucket` limited to its state prefixes, `s3:GetObject`
and `s3:PutObject` on the exact state keys, and `s3:GetObject`, `s3:PutObject` and
`s3:DeleteObject` on their `.tflock` keys. Normal state access does not require deleting
the state object. Bootstrap bucket administration is separate from ordinary environment
provisioning. Application identities get no state-bucket access. There is no CI/CD
trust role yet; CI validates offline with repository read permission only.

## Application boundaries

- PostgreSQL is authoritative. The database subnets have no Internet route and the
  database has no public address. Only the three explicit client groups can connect
  on 5432. There is no compute or connection path from a developer laptop in this
  slice. Do not temporarily expose RDS to perform migrations.
- A later private, one-shot migration task must use explicit Alembic upgrades through
  `0010`, then `alembic check`. Provision separate migration, API and worker database
  roles/grants after reviewing repository locks and append-only triggers. The admin
  secret ARN output is metadata for that operator flow, not an application credential.
  Never fetch the secret value through Terraform or reuse the admin user in runtime.
- Store application credentials in Secrets Manager in the deployment slice. Inject
  `DATABASE_URL` outside source/state and percent-encode credentials. The supported
  shape is `postgresql+psycopg://USER:PASSWORD@RDS_HOST:5432/runveil?sslmode=verify-full&sslrootcert=/run/certs/rds.pem`.
  Package the verified [AWS RDS root CA bundle](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.SSL.html)
  and retain the real RDS hostname for identity verification. `rds.force_ssl=1`
  requires encryption but does not make a client verify the server identity.
- `/health` is process liveness and `/ready` checks database connectivity, not schema
  revision. Do not expose the current local operator endpoints publicly merely
  because TLS exists. Review identity, authorization and proxy routing first.
- The queue URL output is compatible with `runveil_worker.sqs --queue-url`. Attach
  the relay policy only to the relay identity; the consumer policy only to the worker.
  No broad AWS managed policy or queue access for the API is needed. These policies
  are unattached until compute identities are reviewed. They confer no database grants.
- Run the existing `submit`, `publish` and `work` commands only with the
  `fixture-calls-v1` enrollment and a migrated database. Supervising these one-shot
  commands needs bounded polling/backoff and graceful shutdown, not an ECS restart
  loop. Do not route repository, MCP or Docker sandbox profiles into this consumer.
- SQS has at-least-once delivery. A 30-second visibility timeout does not supersede
  the 660-second database lease. Messages may reach the DLQ while valid work is
  deferred. The DLQ alarm is console-only, with no paging or email action. Investigate
  run state before manual redrive; the worker has no DLQ access. See [broker operations](BROKER.md)
  and [AWS DLQ retention semantics](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-dead-letter-queues.html).

## Cost, operations and live acceptance

Before apply, obtain a regional estimate for RDS instance-hours (two instances for
production Multi-AZ), 20 GiB gp3, backups/snapshots, Secrets Manager, SQS requests,
state versions and the CloudWatch alarm. No free-tier eligibility or fixed monthly
price is assumed. Set an account budget/alert before live acceptance. No NAT, ALB,
ECS tasks, ECR, GPU or interface endpoints are provisioned. RDS remains chargeable
while this foundation has no applications; do not leave an acceptance environment
idle. Recurring outbox sends increase SQS requests. Retained backups/snapshots and
state versions still cost money after environment teardown.

Storage does not autoscale. Watch RDS FreeStorageSpace and CPU credits as well as
CPU, memory, connections, queue age, visible messages and DLQ alarm state. This slice
does not install an operations dashboard, notification destination or database alarm
suite. Review supported PostgreSQL minor upgrades deliberately; disabled automatic
minor upgrade does not prevent AWS mandatory lifecycle upgrades. No run payload or
SQL statement logs are exported by this configuration.

Live acceptance remains required in a disposable non-production account:

1. Review account/backend identity, IAM, regional version/class support, plan and cost.
2. Apply, then require a no-change plan. Inspect routes, groups, encryption, secrets,
   backups, queue/redrive and tags in AWS.
3. After private compute/migrations exist, verify CA-checked TLS, rejection of plaintext
   and unauthorized clients, API liveness/readiness and restricted DB role behavior.
4. Exercise relay send, consumer receive/delete, terminal duplicates and restart
   recovery; prove crossed IAM actions and other-environment access are denied.
5. Verify DLQ diagnosis/alerting and snapshot restore, then perform the teardown below.

These are future acceptance gates, not results from mocked tests or local PostgreSQL.

## Deliberate teardown

For non-production, set `allow_database_destroy = true`, review and **apply that
change first** to remove RDS deletion protection. Keep final snapshots enabled.
Choose an unused `final_snapshot_suffix` before each teardown; an existing snapshot
with the same identifier causes deletion to fail. Inspect a saved destroy plan, then
apply it. Source/DLQ messages are deleted with their queues, so collect required
operational evidence first. The database final snapshot and retained automated
backups intentionally survive. Verify them and explicitly remove them only after
retention/restore requirements are satisfied.

Production cannot disable deletion protection via variables; it requires a separately
reviewed code change and recovery plan. Bootstrap state remains outside environment
destruction. Removing a state bucket requires deliberate code changes to its guard,
secure state migration/retention, and explicit removal of all object versions and
locks. Never delete state as a shortcut to resource cleanup. Clean teardown and
snapshot restoration have not yet been tested against AWS.
