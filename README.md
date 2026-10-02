# Runveil

A custom Python runtime for durable, bounded AI-agent execution.

Runveil explores the engineering around model calls: typed tools, persisted
execution, checkpoints, recovery, retries and resource limits. The core runtime
is built directly so its behavior can be inspected and tested.

The goal is a software-engineering agent that investigates a repository and
proposes changes in an isolated environment, with human approval before applying
them. Today, the backend supports durable execution and controlled read-only
repository tools, durable patch reviews and approved single-file replacement in a
controlled local checkout. A local authenticated API and small operator console
expose approval inspection and decisions. A separate read-only trace API and
[trace console](docs/operations/TRACES.md) expose ordered execution evidence and
persisted accounting. Opt-in [execution telemetry](docs/operations/TELEMETRY.md)
adds correlated OpenTelemetry spans and safe JSON output. An offline
[evaluation harness](docs/operations/EVALUATIONS.md) compares immutable configurations
on a versioned public code-reading corpus, with opt-in
[paired statistical reports](docs/operations/STATISTICS.md). These scripted results
verify the harness and statistical methods, not model quality. Hosted approval
flows and real model-quality evaluations remain future work. A [Docker sandbox](docs/operations/SANDBOX.md) supports isolated, bounded fixture
tests through an explicitly authorized durable scripted worker.
A separate review worker inspects the pinned fixture and records exact patch proposals for human review.
A distinct WRITE-authorized sandbox worker applies approved patches and records test/diff evidence.
An integrated [fixture workflow](docs/operations/SANDBOX.md#fixture-engineering-workflow--phase-10e) connects inspection, failing baseline tests, exact review and approved validation in one durable run.
The workflow supports three controlled repairs: clamp bounds, whitespace slugs and fractional means.
The search-enabled workflow now covers the original Phase 10 checklist across three controlled tasks.
The [Phase 10 audit](docs/operations/PHASE_10.md) is ready for bounded-scope closure review.

Reliability is verified with deterministic tests and worker-process crash/recovery
checks. This is a development project, not a production service.

[Architecture](ARCHITECTURE.md) · [Roadmap](ROADMAP.md) ·
[Development guide](docs/operations/DEVELOPMENT.md) ·
[Phase 5 verification](docs/operations/PHASE_5.md) ·
[Phase 6 acceptance](docs/operations/PHASE_6.md) ·
[Phase 7 acceptance](docs/operations/PHASE_7.md) ·
[Phase 8 acceptance](docs/operations/PHASE_8.md) ·
[Phase 9 acceptance](docs/operations/PHASE_9.md) · [Contributing](CONTRIBUTING.md)

[MIT License](LICENSE)

The [product showcase](docs/operations/SHOWCASE.md) presents the recorded Phase 10
workflow at `/` and `/runs`, including exact proposals and test evidence. Live local
trace inspection stays at `/traces`; the existing approval console is at `/approvals`.
