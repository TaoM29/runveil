# Phase 12A handoff: private AWS data foundation

Date: 2026-10-02. Implemented; stopped for review. No commit, push or AWS apply.

## Implementation and decisions

Inspected the clean repository, charter, architecture, roadmap, accepted persistence,
SQS, local API, Docker sandbox and MCP decisions, current application entry points,
CI/development commands and Phase 11 closure evidence before implementation.

The smallest coherent slice is the private data boundary: protected state bootstrap,
isolated networking, encrypted RDS PostgreSQL 17 and an encrypted SQS Standard/DLQ
pair. It intentionally does not create running applications or a public endpoint.
Separate API/worker/migration groups permit only PostgreSQL traffic. Separate,
unattached relay and consumer IAM policies permit only their existing SDK actions
on the source queue. AWS manages the administrator password in Secrets Manager;
Terraform does not generate or read secret values. Production enables Multi-AZ,
longer backup retention and a variable-level prohibition on disabling deletion protection.

[ADR 0042](../adr/0042-private-aws-data-foundation.md) records the scope and trade-offs.
The current sandbox needs Docker host authority unavailable in Fargate, the SQS
commands are one-shot and fixture-only, and the API is still local-operator scoped.
Deployment cannot safely be inferred from infrastructure availability. No runtime
behavior, migrations, Python dependencies, benchmark artifacts or grants changed.
One application boundary test verifies that the existing SQLAlchemy/psycopg path
preserves CA verification options and encoded credentials without making a connection.

## Files created

- `infra/terraform/bootstrap/main.tf`, `.terraform.lock.hcl`,
  `tests/state.tftest.hcl`: account/environment-bound S3 state bucket, encryption,
  versioning, public/ACL denial, TLS-only policy and destruction guard.
- `infra/terraform/environment/versions.tf`, `variables.tf`, `network.tf`,
  `database.tf`, `queue.tf`, `outputs.tf`, `.terraform.lock.hcl`,
  `tests/foundation.tftest.hcl`: backend, pinned provider, inputs, private database,
  queue/IAM/DLQ alarm and offline boundary tests.
- `docs/adr/0042-private-aws-data-foundation.md`.
- `docs/operations/AWS.md`: state bootstrap/migration, environment separation,
  private connection/deployment contracts, cost drivers, live gates and teardown.
- `docs/operations/PHASE_12A.md`: this handoff.

## Files modified

- `.github/workflows/ci.yml`: independent offline Terraform verification job.
- `.gitignore`: local Terraform state, plans, operator variables/backend configuration
  and bootstrap override protection; provider locks remain tracked deliverables.
- `packages/persistence/tests/test_configuration.py`: RDS TLS driver-boundary test.
- `ARCHITECTURE.md`, `ROADMAP.md`: implemented 12A scope and open Phase 12 gates.
- `docs/operations/BROKER.md`, `docs/operations/DEVELOPMENT.md`: infrastructure links
  and current queue provisioning/verification guidance.

## Verification environment

Terraform 1.13.5 was downloaded from HashiCorp into `/tmp/runveil-terraform`, checked
against its published SHA-256 list, and used for all commands below. Provider 6.16.0
installed with verified HashiCorp signatures. Both committed locks include registry
platform checksums; reinitialization with `-lockfile=readonly` passed.

The pre-existing Intel Python environment lacked MCP. Its initial mypy and pytest
collection failed; attempting a locked sync entered the same native cryptography
build issue recorded in Phase 11A and was interrupted. Final checks reused the
already-installed ARM CPython 3.12.14 environment with
`UV_PROJECT_ENVIRONMENT=/tmp/runveil-phase11-venv`; no manifest or lock change.
Node checks used the installed 24.19.0 interpreter via `PATH`.

PostgreSQL used a new disposable Compose project, `runveil-phase12-review`, with
`--env-file /dev/null`, the documented local-only password and port 5432. It did not
reuse another project's database or read local `.env`. `DATABASE_URL` selected its
`runveil` database and `RUNVEIL_TEST_DATABASE_URL` its `postgres` administrative database.
Integration/acceptance commands created and dropped only their owned temporary databases.
The review project's container, network and volume were removed after verification.

## Commands and results

- `terraform fmt -check -recursive infra/terraform`: passed.
- For each of `infra/terraform/bootstrap` and `infra/terraform/environment`:
  `terraform init -backend=false -input=false -lockfile=readonly`,
  `terraform validate`, `terraform test`: passed. **Six test runs** total: protected
  state, private foundation, production protection and three refused configurations.
  All use mocked AWS providers. Initial mock failures exposed test cleanup under
  `prevent_destroy` and missing computed secret metadata; corrected the test setup,
  preserving the infrastructure guards.
- `uv sync --locked --all-packages --python <installed-native-python3.12>`: passed.
- `uv run ruff format --check .` and `uv run ruff check .`: passed, 284 files formatted.
- `uv run mypy`: passed, 148 source files.
- `uv run pytest -m 'not integration'`: **165 passed**.
- `uv run alembic upgrade head` and `uv run alembic check`: passed; no new operations.
- `uv run pytest -m integration`: **212 passed, 11 skipped**. Skips are the existing
  opt-in real-Docker sandbox cases; no sandbox implementation changed in this slice.
- `uv run python scripts/phase5_acceptance.py`: passed both actual SIGKILL cases,
  active-lease deferral, terminal duplicate acknowledgement and disposable DB cleanup.
  SDK stubs exercised queue behavior; no AWS or paid provider call.
- `npm run lint`, `npm run typecheck`, `npm test`: passed; **13 frontend tests**.
- `npm run build`: passed.
- `uv run python scripts/smoke.py`: passed API/web health, showcase/operator routes,
  response protections and database-configured readiness.
- `npm run format:check` and `git diff --check`: passed.

Terraform tests verify configuration and policy expressions, not live IAM/service
behavior. No AWS backend initialization, real plan/apply/destroy, RDS TLS handshake,
regional version/class availability, snapshot restore, live SQS delivery or cloud
application health was tested. The separate Docker boundary acceptance was not rerun;
its eleven opted-out integration cases remain a stated gap, not a claimed pass.
Hosted CI has not run on these uncommitted changes.

## Remaining concerns and recommended next slice

Phase 12 remains open. ECR/ECS, immutable application containers, database users/grants,
application secrets, private migration access, worker supervision, authenticated
network exposure, notification destinations and live cost/restore/teardown evidence
are not yet implemented. RDS has recurring cost even without compute; only provision
after reviewing the account and regional estimate. Retained snapshots/backups and
state intentionally survive teardown. The DLQ alarm has no notification action.
Manual region/backend inputs and IAM attachment still require operator review.

After reviewing this slice, package the API and fixed fixture SQS path for private
compute, with separate migration/runtime database roles and task identities. Verify
health and bounded supervision before exposing endpoints. Keep Docker-dependent
profiles out of that Fargate slice. Stop here for review.
