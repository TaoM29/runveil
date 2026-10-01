"""Sequential offline batches; execution and authorization remain owned by the runtime."""

import hashlib
import sys
from datetime import UTC, datetime
from importlib import import_module
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID, uuid4

from runveil_core.invocations import InvocationStatus
from runveil_core.models import ModelResponse, TokenUsage
from runveil_core.runs import RunStatus
from runveil_core.runtime import execute
from runveil_core.scripted import ScriptedProvider
from runveil_core.tools import ToolRegistry
from runveil_persistence.execution import PostgresExecutionStore, load_runtime_state
from runveil_persistence.jobs import claim_next, enroll
from runveil_persistence.repositories import AgentRepository, RunRepository
from runveil_persistence.traces import read_trace
from runveil_tools.repository import RepositoryAccess, RepositoryTools
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runveil_evaluations.contracts import (
    Comparison,
    EvalCase,
    EvalCaseResult,
    EvalRun,
    EvalSuite,
    compare,
    digest,
)
from runveil_evaluations.fixtures import POLICY, SUITE, configuration


def implementation_digest() -> str:
    """Fingerprint source-backed execution/evaluator packages and relevant dependencies."""
    checksum = hashlib.sha256(b"runveil-evaluation-implementation-v1\0")
    for package in ("runveil_core", "runveil_persistence", "runveil_tools", "runveil_evaluations"):
        source = import_module(package).__file__
        if source is None:
            raise RuntimeError("Evaluation requires source-backed packages")
        root = Path(source).parent
        for path in sorted(root.rglob("*.py")):
            checksum.update(f"{package}/{path.relative_to(root)}\0".encode())
            checksum.update(path.read_bytes())
            checksum.update(b"\0")
    checksum.update(sys.version.encode())
    for dependency in ("pydantic", "pydantic-core", "sqlalchemy", "psycopg", "opentelemetry-api"):
        checksum.update(f"\0{dependency}={version(dependency)}".encode())
    return checksum.hexdigest()


async def score_case(
    sessions: async_sessionmaker[AsyncSession],
    case: EvalCase,
    run_id: UUID,
    agent_version_id: UUID,
) -> EvalCaseResult:
    async with sessions.begin() as session:
        await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        trace = await read_trace(session, run_id, limit=100)
        state = await load_runtime_state(session, run_id)
    if (
        state is None
        or trace.agent_version_id != agent_version_id
        or trace.status not in (RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED)
        or not trace.history_complete
        or trace.next_after_sequence is not None
        or trace.elapsed_ms is None
        or trace.checkpoint is None
        or trace.checkpoint.tokens is None
        or trace.checkpoint.cost is None
    ):
        raise ValueError("Evaluation requires complete terminal evidence with accounting")
    tool_calls = tuple(
        event.invocation
        for event in trace.events
        if event.invocation is not None
        and event.invocation.kind == "tool"
        and event.sequence == event.invocation.requested_sequence
    )
    grade: str
    if trace.status != RunStatus.SUCCEEDED:
        grade = "runtime_failure"
    elif state.final_result is None or state.final_result.summary != case.expected_summary:
        grade = "summary_mismatch"
    elif tuple(call.name for call in tool_calls) != case.expected_tools or any(
        call.status != InvocationStatus.SUCCEEDED for call in tool_calls
    ):
        grade = "tool_mismatch"
    else:
        grade = "pass"
    return EvalCaseResult.model_validate(
        {
            "case_id": case.id,
            "run_id": run_id,
            "status": trace.status,
            "grade": grade,
            "error_code": trace.checkpoint.error_code,
            "event_sequence": trace.event_sequence,
            "steps": state.steps_used,
            "model_calls": trace.model_calls,
            "tool_calls": trace.tool_calls,
            "retries": state.retries_scheduled,
            "elapsed_ms": trace.elapsed_ms,
            "tokens": trace.checkpoint.tokens,
            "cost": trace.checkpoint.cost,
        }
    )


async def run_suite(
    sessions: async_sessionmaker[AsyncSession],
    suite: EvalSuite,
    *,
    agent_id: UUID,
    max_steps: int,
    implementation: str,
) -> EvalRun:
    config = configuration(max_steps)
    started = datetime.now(UTC)
    async with sessions.begin() as session:
        agent_version = await AgentRepository(session).create_version(
            agent_id, config.model_dump(mode="json")
        )
    results = []
    for case in suite.cases:
        # Only public suite bytes are written. Model paths never reach this writer.
        with TemporaryDirectory(prefix="runveil-eval-") as temporary:
            root = Path(temporary)
            (root / "example.py").write_text(case.file_content, encoding="utf-8")
            with RepositoryTools(root, access=RepositoryAccess(files=("example.py",))) as repo:
                async with sessions.begin() as session:
                    run = await RunRepository(session).create(agent_version.id)
                    await enroll(session, run.id, task=case.task, profile="eval-calibration-v1")
                claim = await claim_next(sessions, profile="eval-calibration-v1", run_id=run.id)
                if claim is None:
                    raise ValueError("Evaluation could not claim its new run")
                provider = ScriptedProvider(
                    [
                        ModelResponse(
                            model=config.model,
                            content=response,
                            finish_reason="stop",
                            usage=TokenUsage(input_tokens=10, output_tokens=5),
                            latency_ms=0.0,
                        )
                        for response in case.responses
                    ]
                )
                await execute(
                    run.id,
                    case.task,
                    tools=ToolRegistry(repo.bindings()),
                    tool_policy=POLICY,
                    provider_name="scripted",
                    provider=provider,
                    store=PostgresExecutionStore(sessions, claim=claim, expected_config=config),
                )
        results.append(await score_case(sessions, case, run.id, agent_version.id))
    return EvalRun(
        id=uuid4(),
        suite_digest=digest(suite),
        implementation_digest=implementation,
        agent_version_id=agent_version.id,
        agent_version_number=agent_version.number,
        configuration=config,
        started_at=started,
        finished_at=datetime.now(UTC),
        cases=tuple(results),
    )


async def run_calibration(sessions: async_sessionmaker[AsyncSession]) -> Comparison:
    implementation = implementation_digest()
    async with sessions.begin() as session:
        agent = await AgentRepository(session).create("Offline evaluation calibration")
    baseline = await run_suite(
        sessions, SUITE, agent_id=agent.id, max_steps=3, implementation=implementation
    )
    candidate = await run_suite(
        sessions, SUITE, agent_id=agent.id, max_steps=5, implementation=implementation
    )
    if implementation_digest() != implementation:
        raise ValueError("Implementation changed during evaluation")
    return compare(SUITE, baseline, candidate)
