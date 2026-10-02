# Private runtime deployment: Phase 12B

This runbook extends the [Phase 12A foundation](AWS.md). The code and local acceptance
are implemented; no AWS environment has been deployed. See [ADR 0043](../adr/0043-private-fixture-deployment.md)
and the [handoff](PHASE_12B.md). Use only a reviewed non-production environment for
initial live acceptance. No command below is part of normal application startup.

## Scope and cost

The deployment has one private TLS API, one fixed-fixture consumer, one relay, and a
one-shot migration task. Each task uses 0.25 vCPU and 512 MiB. Existing PostgreSQL
and SQS remain authoritative data/notification infrastructure. The API is read-only;
there is no approval, submission, web, provider, repository, MCP or sandbox deployment.

`enable_private_runtime=false` preserves foundation-only behavior. Enabling it creates
five chargeable interface endpoints even with all services stopped: ECR API, ECR DKR,
Logs, Secrets Manager and SQS. Non-production provisions those endpoints in one AZ;
production provisions them in both AZs. Include endpoint-hours, cross-AZ traffic,
three Fargate tasks, retained ECR images, Secrets Manager and bounded CloudWatch logs
in the regional estimate alongside RDS, SQS and state costs. No NAT, load balancer,
GPU, collector or Container Insights is installed. No free tier or fixed price is assumed.

There is one replica per service, no rollout surge and no API availability promise.
Production Multi-AZ data/endpoints do not make a single API replica highly available.
Keep account budget notifications enabled. Review queue age, failed iterations and
DLQ state manually during acceptance; the existing DLQ alarm still has no notification
action. Worker process health is not proof of queue progress.

## Build and local checks

Use the pinned tool versions in the [development guide](DEVELOPMENT.md). The build
context is allowlisted, excluding `.env`, local state, skills, credentials and tests.
Both base images use immutable manifest digests; Python dependencies use `uv.lock`.
The final image contains non-editable installed packages, migrations, the fixed
entrypoint and the public [RDS root bundle](../../deploy/certs/README.md).

```sh
docker build --platform linux/amd64 -f deploy/Dockerfile -t runveil-runtime:phase12b .
RUNVEIL_RUNTIME_IMAGE=$(docker image inspect runveil-runtime:phase12b --format '{{.Id}}')
uv run python scripts/cloud_smoke.py --image "$RUNVEIL_RUNTIME_IMAGE"
```

The smoke requires Docker and OpenSSL. It creates uniquely named disposable
containers/network, generates temporary test certificates/passwords, runs explicit
migrations and fixture submission, checks authenticated TLS trace access from a
separate client, runs the container health probe, and stops relay/worker via SIGTERM.
Its internal network has no AWS access. It does not touch a developer database or
use real cloud secrets. Owned containers/volumes/network and temporary secrets are
removed at completion. An interrupted/killed harness may need operator cleanup of
its printed/discoverable `runveil-cloud-*` resources; never prune unrelated resources.

For real PostgreSQL grant and queue acceptance, set `RUNVEIL_TEST_DATABASE_URL` to
an isolated admin database and run:

```sh
uv run pytest packages/persistence/tests/test_deployment.py apps/api/tests/test_private_deployment.py
```

The role test refuses to modify pre-existing `runveil_api`, `runveil_worker`,
`runveil_relay` or `runveil_test_migrator` roles. Use a disposable cluster if it skips.
It verifies a full fixture run through restricted roles with offline SDK stubs,
including duplicate acknowledgement and denied DDL/history deletion/crossed access.
Run the Terraform checks from [AWS operations](AWS.md); Linux and Mac provider
checksums remain locked. CI adds the production image build and disposable smoke.

## Release sequence

Use separate production/non-production AWS accounts and the existing state workflow.
Short-lived operator credentials need reviewed ECR upload, secret population and
specific ECS RunTask/PassRole/Describe permissions. Neither ordinary application task
roles nor the read-only GitHub CI identity should receive these powers. Restrict
PassRole to these environment-specific roles and ECS tasks; arbitrary command overrides
on the migration task carry administrator database authority.

1. **Provision dependencies, stopped.** Set `enable_private_runtime=true`, leave
   `runtime_image_digest=null` and `activate_runtime=false`, review a saved plan,
   then apply it. This creates the ECR repository, secret containers, roles, cluster,
   private application subnets/endpoints and logs. No tasks run yet. Review the
   `private_runtime` output for ARNs and network IDs. Confirm the account and region.
2. **Populate secrets outside Terraform.** Generate three distinct 32-byte random
   hex passwords (64 lowercase hex characters), one per `api-db`, `worker-db`,
   `relay-db` secret, each as `{"password":"..."}`. Populate `api-access` as a JSON
   object with `trace_token` (43–128 URL-safe characters), `tls_certificate` (PEM full
   chain) and `tls_key` (unencrypted matching PEM private key). Use an approved private
   CA/certificate hostname for operator clients. Never paste secret values into shell
   arguments, tfvars, plans, logs or source. Use an approved secret-entry workflow or
   a mode-0600 temporary file with the AWS CLI's `--secret-string file://...`, then
   remove the local copy. Terraform creates no secret versions and never reads values.
3. **Build and push the reviewed image.** Authenticate Docker to the output ECR
   repository with short-lived credentials, tag the image with the reviewed Git SHA,
   and push it. Obtain the registry image digest; the local Docker image ID is not
   the deployment manifest digest. Set `runtime_image_digest="sha256:..."`. Use only
   this environment's ECR repository, Linux AMD64 and the pinned Dockerfile. Review
   scan findings before using the image. No mutable `latest` deployment is supported.
4. **Register tasks, still stopped.** Apply with `activate_runtime=false`. This
   registers API/worker/relay/migration task definitions and zero-replica services.
5. **Run migration explicitly.** Use the exact migration task ARN, application subnet
   IDs and migration security group from `private_runtime`; public IP must be DISABLED.
   Run once, wait for STOPPED, then require the `migration` container's exit code 0
   and `migration_succeeded` log marker. A successful RunTask request is not evidence
   of migration success. Inspect failures without dumping secret environment values.
6. **Activate only the migrated image.** Set `migration_image_digest` to that exact
   successful image digest and `activate_runtime=true`; review/apply the saved plan.
   Terraform rejects missing/mismatched attestations. All processes also verify the
   database revision at startup. Wait for services to stabilize, then perform live
   acceptance below. Terraform's attestation is operator evidence, not an automated
   cross-check against ECS history.

Example migration invocation after substituting the output values into local shell
variables; none of these variables contain credentials:

```sh
aws ecs run-task --cluster "$RUNVEIL_CLUSTER" \
  --task-definition "$RUNVEIL_MIGRATION_TASK" --launch-type FARGATE \
  --platform-version 1.4.0 \
  --network-configuration "awsvpcConfiguration={subnets=[$RUNVEIL_SUBNET],securityGroups=[$RUNVEIL_MIGRATION_GROUP],assignPublicIp=DISABLED}"
aws ecs wait tasks-stopped --cluster "$RUNVEIL_CLUSTER" --tasks "$RUNVEIL_TASK_ARN"
aws ecs describe-tasks --cluster "$RUNVEIL_CLUSTER" --tasks "$RUNVEIL_TASK_ARN" \
  --query 'tasks[].{stopCode:stopCode,containers:containers[].{name:name,exitCode:exitCode,reason:reason}}'
```

The one-shot task injects the RDS-managed administrator username/password and the
three runtime passwords. Migration upgrades through `0010`, runs Alembic metadata
checks and reconciles grants in one transaction under a migration lock. It does not
run at service startup. The same operator-only task can enroll one fixed acceptance
run with `--overrides '{"containerOverrides":[{"name":"migration","command":["submit"]}]}'`.
That command prints the run ID and only writes PostgreSQL; the separate relay sends
notifications. There is no HTTP submission route and the consumer cannot create jobs.

## Runtime authority and access

| Process        | Database authority                                                          | AWS task authority          | Injected secrets                                  |
| -------------- | --------------------------------------------------------------------------- | --------------------------- | ------------------------------------------------- |
| API            | Read trace tables and revision                                              | None                        | API DB password, trace token, TLS certificate/key |
| Consumer       | Read runtime records, update ownership/run/invocation state, append history | Source queue receive/delete | Consumer DB password                              |
| Relay          | Read eligibility/outbox, update publication/lease columns                   | Source queue send           | Relay DB password                                 |
| Migration task | Database owner and role provisioning                                        | None                        | RDS admin and all three runtime DB passwords      |

Execution roles are separate from these application roles. They pull only the
reviewed ECR repository, write their own log group and retrieve only their listed
secrets. `ecr:GetAuthorizationToken` is the necessary wildcard-resource exception;
it grants no repository push or unrelated image read. Endpoint policies add caller
and service limits. No API/consumer/relay gets the RDS administrator secret or any
Terraform state access. IAM task roles do not fetch secrets directly.

Table privileges are not row-level or tenant isolation. Keep this environment scoped
to the fixed fixture. Runtime roles own no schema/tables and receive no CREATE,
TRUNCATE, DELETE, trigger-disable or role-management grants. The migration task is
privileged and must remain an explicit operator action. Never point it at an unrelated
shared database or reuse these fixed role names in another database on the instance.

The database subnets remain isolated. Application traffic can reach PostgreSQL on
5432, the reviewed endpoints on 443 and the ECR layer bucket through S3. There is no
Internet route, arbitrary provider access or public address. The API operator group
has only TLS 8443 access to the API group. Attach it only to a separately approved
private operator client. This slice does not create that client, VPN, bastion or ALB.
Do not attach the migration/database group just to inspect API health.

Use ECS DescribeTasks/DescribeNetworkInterfaces to discover the current API task's
private IP; it changes on replacement. From the approved private client, use the
certificate's hostname and a trusted CA. For example:

```sh
curl --cacert /secure/operator-ca.pem \
  --resolve "$RUNVEIL_API_HOSTNAME:8443:$RUNVEIL_API_PRIVATE_IP" \
  "https://$RUNVEIL_API_HOSTNAME:8443/ready"
```

Use a protected client credential store for authenticated trace requests, not a token
in command arguments/history. `/health` reports liveness; `/ready` checks connectivity.
Startup checks schema revision, but readiness does not continually audit it. Do not
run migrations behind live services. There are no approval, submission or docs routes;
normal local API behavior remains unchanged. The in-container health probe trusts
the installed certificate and skips only loopback hostname matching. Live clients
must verify both the CA and the intended hostname.

## Updates, failure handling and live gates

Before changing images, database passwords or schema, apply `activate_runtime=false`
and wait for all three services to stop. Build/register the new image, run its migration,
then attest/activate it. Password reconciliation intentionally does not implement
zero-downtime dual credentials. For API token/certificate rotation, populate a new
secret version and restart the API; ECS does not refresh injected secrets in-place.
Check certificate expiry and deliberately refresh the vendored RDS roots when needed.

A migration failure leaves services stopped. A revision mismatch fails startup rather
than performing implicit upgrades. Deployment circuit breaking is enabled, but every
release still needs health/recovery review. Rollback to a prior immutable image only
if compatible with the current schema and credential state. Never downgrade history
or rewrite immutable run configuration to make a rollback pass.

Relay and worker back off after fixed, redacted error logs; they do not abandon
PostgreSQL leases or change recovery semantics. SIGTERM drains up to 80 seconds,
then cancels cooperative work before ECS's 120-second stop limit. Busy calls may leave
uncertain intent, which existing recovery fails without replay. Repeated notification
publication and duplicate acknowledgement remain unchanged. Workers do not have DLQ
administration or profile-selection input. Investigate stalls/DLQ evidence explicitly.

Before declaring Phase 12 complete, demonstrate live private endpoint image pull,
secret injection, RDS CA verification and restricted-role migrations, API TLS/identity,
fixed-run completion/duplicate delivery, restart recovery, crossed IAM denials and
other-environment denial, credential/certificate rotation, snapshot restoration,
rollout/rollback and teardown. Local mocks and Docker evidence do not establish those
AWS behaviors or quotas. Review ECR scan findings and regional cost before live use.

For teardown, stop services first. ECR refuses deletion while images remain: review
retention/rollback requirements and explicitly remove images before destruction.
Secrets have a seven-day recovery window; pending deletion can block immediate name
reuse. Logs, service tasks, endpoints and application subnets are Terraform-owned.
Keep the Phase 12A snapshot/state protections and account for retained backup cost.
No live teardown, secret recovery or snapshot restore is claimed yet.
