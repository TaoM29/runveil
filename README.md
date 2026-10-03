# Runveil

> This repository is under active development.

A custom Python runtime for durable, bounded AI-agent execution. Runveil is building
toward a software-engineering agent that investigates a repository, proposes a
patch, waits for human approval, and validates the change in an isolated environment.
The project owns the execution loop, persistence, recovery, and authorization logic.

## Where we are

**Now: Phase 12, private AWS deployment.** The runtime and local workflows are
implemented, including sandboxed coding tasks and read-only MCP tools. Terraform
and container configuration are implemented through Phase 12B, with local and
offline verification. Live AWS acceptance is pending; this is not a production service.

What works today:

- Durable execution with checkpoints, crash recovery, bounded retries, and limits
  on steps, time, tokens, estimated cost, and tool calls.
- Typed repository read/search tools, read-only MCP integration, and human approval
  bound to the exact proposed patch before controlled writes.
- Docker-isolated coding workflows across three controlled tasks: inspect, search,
  run failing tests, propose a repair, approve, apply, and validate.
- Local approval and trace consoles, execution telemetry, and an offline evaluation
  harness with paired statistical comparisons.

The web [showcase](docs/operations/SHOWCASE.md) at `/` and `/runs` presents recorded
public fixture runs. Local operator tools live at `/approvals` and `/traces`.
Scripted fixtures verify runtime behavior; they do not establish general coding-agent
or model quality. Phase 10 and 11 closure reviews remain pending.

## Tech stack

Runtime, data & tools

[![Python](https://img.shields.io/badge/Python-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Pydantic](https://img.shields.io/badge/Pydantic-E92063?logo=pydantic&logoColor=white)](https://docs.pydantic.dev/)
[![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-D71F00?logo=sqlalchemy&logoColor=white)](https://www.sqlalchemy.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![MCP](https://img.shields.io/badge/MCP-222222?logo=modelcontextprotocol&logoColor=white)](https://modelcontextprotocol.io/docs/getting-started/intro)

Web

[![Next.js](https://img.shields.io/badge/Next.js-000000?logo=nextdotjs&logoColor=white)](https://nextjs.org/)
[![React](https://img.shields.io/badge/React-20232A?logo=react&logoColor=61DAFB)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-0F172A?logo=tailwindcss&logoColor=38BDF8)](https://tailwindcss.com/)
[![Node.js](https://img.shields.io/badge/Node.js-339933?logo=nodedotjs&logoColor=white)](https://nodejs.org/)
[![npm](https://img.shields.io/badge/npm-CB3837?logo=npm&logoColor=white)](https://docs.npmjs.com/)

Development, testing & observability

[![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![Docker Compose](https://img.shields.io/badge/Docker_Compose-2496ED?logo=docker&logoColor=white)](https://docs.docker.com/compose/)
[![uv](https://img.shields.io/badge/uv-5B21B6?logo=uv&logoColor=white)](https://docs.astral.sh/uv/)
[![Ruff](https://img.shields.io/badge/Ruff-5B21B6?logo=ruff&logoColor=white)](https://docs.astral.sh/ruff/)
[![pytest](https://img.shields.io/badge/pytest-0A9EDC?logo=pytest&logoColor=white)](https://docs.pytest.org/)
[![Vitest](https://img.shields.io/badge/Vitest-467522?logo=vitest&logoColor=white)](https://vitest.dev/)
[![ESLint](https://img.shields.io/badge/ESLint-4B32C3?logo=eslint&logoColor=white)](https://eslint.org/)
[![Prettier](https://img.shields.io/badge/Prettier-333333?logo=prettier&logoColor=white)](https://prettier.io/)
[![OpenTelemetry](https://img.shields.io/badge/OpenTelemetry-425CC7?logo=opentelemetry&logoColor=white)](https://opentelemetry.io/)
[![GitHub Actions](https://img.shields.io/badge/GitHub_Actions-2088FF?logo=githubactions&logoColor=white)](https://github.com/features/actions)

Cloud infrastructure (configured; live acceptance pending)

[![AWS](https://custom-icon-badges.demolab.com/badge/AWS-232F3E?logo=aws&logoColor=white)](https://aws.amazon.com/)
[![Terraform](https://img.shields.io/badge/Terraform-844FBA?logo=terraform&logoColor=white)](https://developer.hashicorp.com/terraform)
[![ECS](https://custom-icon-badges.demolab.com/badge/ECS-232F3E?logo=aws&logoColor=white)](https://aws.amazon.com/ecs/)
[![Fargate](https://custom-icon-badges.demolab.com/badge/Fargate-232F3E?logo=aws&logoColor=white)](https://aws.amazon.com/fargate/)
[![ECR](https://custom-icon-badges.demolab.com/badge/ECR-232F3E?logo=aws&logoColor=white)](https://aws.amazon.com/ecr/)
[![RDS](https://custom-icon-badges.demolab.com/badge/RDS-232F3E?logo=aws&logoColor=white)](https://aws.amazon.com/rds/)
[![SQS](https://custom-icon-badges.demolab.com/badge/SQS-232F3E?logo=aws&logoColor=white)](https://aws.amazon.com/sqs/)
[![S3](https://custom-icon-badges.demolab.com/badge/S3-232F3E?logo=aws&logoColor=white)](https://aws.amazon.com/s3/)
[![CloudWatch](https://custom-icon-badges.demolab.com/badge/CloudWatch-232F3E?logo=aws&logoColor=white)](https://aws.amazon.com/cloudwatch/)
[![IAM](https://custom-icon-badges.demolab.com/badge/IAM-232F3E?logo=aws&logoColor=white)](https://aws.amazon.com/iam/)
[![Secrets Manager](https://custom-icon-badges.demolab.com/badge/Secrets_Manager-232F3E?logo=aws&logoColor=white)](https://aws.amazon.com/secrets-manager/)

Planned inference experiments

[![vLLM](https://img.shields.io/badge/vLLM-333333?logo=vllm&logoColor=white)](https://docs.vllm.ai/)
[![EC2 GPU](https://custom-icon-badges.demolab.com/badge/EC2_GPU-232F3E?logo=aws&logoColor=white)](https://aws.amazon.com/ec2/instance-types/#Accelerated_Computing)

| Layer                      | In place                                                                                     | Remaining                                                    |
| -------------------------- | -------------------------------------------------------------------------------------------- | ------------------------------------------------------------ |
| Runtime & API              | Python 3.12, Pydantic, FastAPI; custom agent loop and workers                                | Broader agent workflows beyond controlled fixtures           |
| Persistence & delivery     | PostgreSQL, SQLAlchemy, Alembic; SQS notification adapter                                    | Live AWS delivery and recovery acceptance                    |
| Web                        | Next.js, React, TypeScript, Tailwind CSS                                                     | Public deployment                                            |
| Models & tools             | Scripted and hosted OpenAI-compatible providers, MCP Python SDK, Docker sandbox              | Temporary GPU-hosted vLLM and inference benchmarks           |
| Observability & evaluation | OpenTelemetry, persisted traces, offline evaluations and paired statistics                   | Real model-quality evaluation                                |
| Infrastructure             | Terraform for private RDS, SQS, ECS/Fargate, ECR, S3 state, Secrets Manager, CloudWatch logs | Live provisioning, health, recovery, IAM and teardown checks |
| Quality & delivery         | GitHub Actions, pytest, Ruff, mypy, Vitest, ESLint, Prettier; image and Terraform checks     | Automated production delivery with AWS OIDC                  |

The AWS configuration currently targets a private read-only API and a fixed scripted
worker workflow. Hosting the web app, models, MCP servers, and Docker sandbox workers
is outside that deployment slice.

## What's next

1. Review Phase 12B and run bounded private AWS acceptance: migrations, TLS health,
   queue delivery, worker recovery, permission boundaries, and cleanup.
2. Automate production delivery, then benchmark temporary self-hosted inference
   with vLLM.
3. Complete security hardening and publish a live demo with reproducible evidence.

See the [roadmap](ROADMAP.md) for review gates and the
[AWS runbook](docs/operations/AWS_RUNTIME.md) for the immediate next slice.

## Explore or run locally

Start with the [development guide](docs/operations/DEVELOPMENT.md) for setup and
verification. Local development uses Python/uv, Node.js/npm, and Docker Compose.

[Architecture](ARCHITECTURE.md) · [Project charter](docs/PROJECT_PLAN.md) ·
[Contributing](CONTRIBUTING.md) · [MIT License](LICENSE)
