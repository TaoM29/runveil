# Runveil

A custom Python runtime for durable, bounded AI-agent execution.

Runveil explores the engineering around model calls: typed tools, persisted
execution, checkpoints, recovery, retries and resource limits. The core runtime
is built directly so its behavior can be inspected and tested.

The goal is a software-engineering agent that investigates a repository and
proposes changes in an isolated environment, with human approval before applying
them. Today, the backend supports durable execution and controlled read-only
repository tools, plus a local durable patch-review workflow. Patch application,
model-driven approval, sandboxed changes and evaluation remain future work; the API
and web console are still foundations.

Reliability is verified with deterministic tests and worker-process crash/recovery
checks. This is a development project, not a production service.

[Architecture](ARCHITECTURE.md) · [Roadmap](ROADMAP.md) ·
[Development guide](docs/operations/DEVELOPMENT.md) ·
[Phase 5 verification](docs/operations/PHASE_5.md) ·
[Phase 6A review](docs/operations/PHASE_6A.md) · [Contributing](CONTRIBUTING.md)

[MIT License](LICENSE)
