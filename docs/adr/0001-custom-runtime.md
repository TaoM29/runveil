# ADR 0001: Build the core runtime directly

- Status: Accepted for initial architecture
- Date: 2026-09-25

## Context

The portfolio must demonstrate understanding of execution state, retries,
checkpoints, budgets, authorization and approvals. Starting with a framework that
owns those mechanisms would conceal the primary engineering artifact.

## Decision

Implement a small custom Python runtime, single-agent-first. Use established
libraries for HTTP APIs, schema validation, persistence, provider clients,
telemetry and MCP protocol support. No runtime code is implemented in Phase 0.

## Alternatives

LangGraph, CrewAI and AutoGen can accelerate applications, but their orchestration
models would own decisions this project intends to expose and test. A future
adapter/comparison experiment is permitted without making a framework the core.

## Trade-offs and consequences

We accept more implementation and reliability-testing work in exchange for clear
ownership of execution semantics. Avoid generic framework scope: implement only
what the controlled repository-task application and failure tests require. Typed
boundaries and deterministic scripted providers will make behavior testable.
