# Phase 12B handoff: private API and fixed-fixture deployment

Date: 2026-10-02. Implementation and local verification complete; **ready for review**. No commit, push, AWS apply or public exposure.

## Implementation

Inspected the charter, architecture, roadmap, Phase 12A Terraform and accepted
ADR 0042, current PostgreSQL migrations/triggers, local API and fixed SQS worker
before extending the same environment root. [ADR 0043](../adr/0043-private-fixture-deployment.md)
records the choices; [AWS runtime operations](AWS_RUNTIME.md) provides the staged
release, credential, migration, cost, recovery and teardown workflow.

The opt-in runtime creates ECR, four secret containers, per-process logs and
execution/task identities, a Fargate cluster, private endpoints/application subnets,
three zero-replica services and an explicit one-shot migration definition. Enabling
replicas requires a digest-pinned image and matching migration success attestation.
No secret values are stored/read by Terraform. Existing foundation-only users incur
no new runtime resources until opting in. No NAT, public IP, ALB, GPU, web, hosted
provider, general submission or Docker-dependent profile is added.

The image serves private TLS health/readiness and authenticated read-only traces.
It does not register approval/submission/docs routes. API/consumer/relay use distinct
unprivileged database users; only the migration task gets the RDS administrator
credential. Explicit migrations check metadata and reconcile table/column grants in
one transaction under a migration lock. Runtime startup checks the expected schema.
Role reconciliation rejects elevated attributes, memberships and object ownership.
Database connections enforce CA and hostname verification using a vendored public
AWS RDS root bundle.

The relay and consumer reuse the existing fixed-fixture broker functions with bounded
polling/backoff, redacted failure output and SIGTERM draining. PostgreSQL claims,
checkpoint recovery, uncertain-intent handling and terminal acknowledgements remain
unchanged. The API task has no AWS task policy; queue actions remain separated between
relay and consumer. Execution roles independently scope ECR/log/secret access.

## Files created

- `infra/terraform/environment/runtime.tf`, `runtime_iam.tf`, `runtime_network.tf`,
  `tests/runtime.tftest.hcl`: runtime resources and credential-free boundary tests.
- `deploy/Dockerfile`, `deploy/Dockerfile.dockerignore`, `deploy/certs/rds.pem`,
  `deploy/certs/README.md`: pinned image, allowlisted context and public trust roots.
- `apps/api/src/runveil_api/private.py`: read-only private API surface.
- `apps/worker/src/runveil_worker/service.py`: fixed broker supervision.
- `packages/persistence/src/runveil_persistence/deployment.py`: verified database
  configuration, schema startup gate and explicit migration/grant reconciliation.
- `scripts/cloud_entrypoint.py`, `scripts/cloud_smoke.py`: fixed image commands and
  disposable TLS/container acceptance.
- `packages/persistence/tests/test_deployment.py`,
  `apps/api/tests/test_private_deployment.py`: real role boundary and private service tests.
- `docs/adr/0043-private-fixture-deployment.md`, `docs/operations/AWS_RUNTIME.md`,
  `docs/operations/PHASE_12B.md`.

## Files modified

- `infra/terraform/environment/variables.tf`, `network.tf`,
  `tests/foundation.tftest.hcl`: opt-in controls, relay database group and default-off test.
- `.github/workflows/ci.yml`: image build and private TLS Docker acceptance.
- `ARCHITECTURE.md`, `ROADMAP.md`, `docs/operations/AWS.md`, `BROKER.md`,
  `DEVELOPMENT.md`: current boundaries and runbook links.

No application dependency, lockfile, database migration revision, benchmark artifact
or existing local API route changed. The current schema revision remains `0010`.

## Verification performed

Python checks used native CPython 3.12.14 via
`UV_PROJECT_ENVIRONMENT=/tmp/runveil-phase11-venv`; Node used 24.19.0.
Terraform used pinned 1.13.5 and AWS provider 6.16.0 with unchanged Linux/Mac lock
hashes. The disposable `runveil-phase12b` Compose project used local-only credentials,
`--env-file /dev/null` and port 55412, avoiding unrelated projects/databases.
The test admin URL was `postgresql+psycopg://runveil:runveil-local-only@127.0.0.1:55412/postgres`;
application migration/smoke used the same local connection with database `runveil`.

- `uv run ruff format --check .`: 298 files already formatted.
- `uv run ruff check .`: passed.
- `uv run mypy`: passed, 155 source files.
- `uv run pytest -q --tb=short` with the disposable test admin URL:
  **380 passed, 11 Docker cases skipped**; those cases are checked separately below.
- Focused `pytest packages/persistence/tests/test_deployment.py apps/api/tests/test_private_deployment.py -q --tb=short`:
  **3 passed** on the final code. Migrations ran twice through a non-superuser database
  owner. Restricted roles completed fixture publication/execution, duplicate
  acknowledgement and trace projection; crossed grants and schema mismatch were refused.
- `uv run alembic upgrade head` and `uv run alembic check`: passed, no metadata drift.
- Terraform `fmt -check -recursive`, `init -backend=false -input=false -lockfile=readonly`,
  `validate` and `test` in both roots under Linux AMD64: **1 bootstrap and 9 environment
  test runs passed**. Lockfiles remained byte-identical. This includes distinct mocked
  role identities, default-off resources, staged activation and rejected mutable images.
- `docker build --platform linux/amd64 -f deploy/Dockerfile -t runveil-runtime:phase12b-amd64 .`:
  passed. Final local image ID is
  `sha256:088429fec6fd2d82f069b067060409b6a5f621871030493fba25ff581302a08c`.
- The `scripts.cloud_smoke.smoke` harness against that image: **passed completely**.
  Explicit migration and fixture enrollment used verified PostgreSQL TLS; the private
  API passed certificate validation, authenticated trace access, unauthorized/absent
  route checks and its health probe. Relay/consumer initialized and exited with code 0
  after SIGTERM on a network with no AWS access. Owned resources were removed.
- `uv run python scripts/phase5_acceptance.py`: checkpoint and uncertain-intent
  SIGKILL recovery, active-lease deferral and duplicate acknowledgement passed;
  its disposable database was removed.
- `docker build --network=none -t runveil-sandbox:phase12b-review sandbox` and
  `uv run python scripts/phase10_sandbox_acceptance.py --image <built-image-id> --output /tmp/runveil-phase12b-sandbox-acceptance.json`:
  passed isolation, failed baseline, watchdog, output limit and cancellation.
- `RUNVEIL_SANDBOX_IMAGE=<built-image-id> uv run pytest` for the four persistence
  sandbox/review/patch/software test modules with `-k real_docker -q --tb=short`:
  **11 passed, 39 deselected**. These are all 11 cases skipped in the full suite.
- `npm run format:check`, `npm run lint`, `npm run typecheck`: passed.
- `npm test`: **13 passed across 6 files**.
- `npm run build`: passed.
- `uv run python scripts/smoke.py` with Node 24 and the disposable application DB:
  passed both real HTTP health contracts, web pages/security headers and API readiness.
- Final documentation formatting and `git diff --check`: passed.

Initial Terraform failures in HCL conditional typing/mock ARN shape were corrected.
The API smoke uses a separate private client container because an internal Docker
network does not publish its port to the host. PostgreSQL's non-superuser role-flag
restrictions led to rejecting unexpected elevated flags and changing only ordinary
login/password/inheritance settings. Final acceptance includes these corrections.

## Storage interruption and cleanup

An earlier image rebuild exhausted local disk space and Docker reported filesystem
I/O errors. Those interrupted runs were not counted as passes. The user freed space
and explicitly authorized a Docker restart; the normal restart stalled, so the
remaining unresponsive Docker process was stopped and Docker Desktop relaunched.
The failed disposable database was removed and recreated before final verification.
No unrelated project data, image or volume was removed.

The interrupted `runveil-cloud-07446cb6e9e0` containers/network were removed. The
successful final smoke used `runveil-cloud-bf72b638c302` and cleaned itself up;
inspection found no remaining `runveil-cloud-*` container or network. Temporary
certificates and generated credentials were local test material and were removed by
the harness. No registry image was pushed.

The `runveil-phase12b` Compose containers, network and disposable database volume
were removed after the final Docker regression cases passed.
Review images are retained locally; no broad image/cache/volume pruning was performed.

## Remaining concerns and next slice

Hosted CI has not run on these uncommitted changes. No live AWS IAM, endpoint routing,
ECR delivery, ECS supervision, RDS migration, certificate/operator access, rotation,
restore or teardown was tested. The migration attestation is manual; table grants
are not tenant isolation; one-replica/no-surge services can be unavailable during
updates; private endpoints incur cost while tasks are stopped; alerts/paging and an
operator access path remain external requirements.

Recommended next slice after review: bounded private non-production AWS acceptance
with a reviewed account, cost estimate and operator connection. Demonstrate live
migration, TLS health, fixture delivery/recovery, crossed IAM denials, rotation and
teardown before expanding public exposure or worker profiles. Phase 12 remains open.
