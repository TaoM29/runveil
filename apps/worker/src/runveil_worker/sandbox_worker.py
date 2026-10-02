"""Explicit durable sandbox tests; no arbitrary commands, workspace or provider."""

import argparse
import asyncio
import json
from pathlib import Path
from uuid import UUID

from runveil_core.models import (
    FinalResult,
    FinishAction,
    ModelRequest,
    ModelResponse,
    TokenUsage,
    ToolAction,
)
from runveil_core.runtime import RuntimeConfig, RuntimeState, execute
from runveil_core.sandbox import (
    SANDBOX_PROFILE,
    TEST_TOOL,
    SandboxIdentity,
    TestsResult,
    authorize_sandbox,
)
from runveil_core.tools import Permission, ToolPolicy
from runveil_persistence.database import create_engine, database_url
from runveil_persistence.execution import ConfigurationRejected, PostgresExecutionStore
from runveil_persistence.jobs import claim_next, enroll
from runveil_persistence.models import ModelInvocationRow, ToolCallRow
from runveil_persistence.repositories import AgentRepository, RunRepository
from runveil_tools.sandbox_execution import BoundSandbox
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runveil_worker.telemetry import telemetry
from runveil_worker.worker import CALLS_PROFILE, configuration

POLICY = ToolPolicy(allowed_tools=(TEST_TOOL,), permissions=(Permission.EXECUTE,))
TASK = "Run the fixed clamp baseline tests in the pinned sandbox and report their observed status."


def sandbox_configuration(identity: SandboxIdentity) -> RuntimeConfig:
    base = configuration(CALLS_PROFILE)
    assert base.pricing is not None
    return RuntimeConfig.model_validate(
        base.model_dump()
        | {
            "schema_version": 12,
            "sandbox": identity,
            "tool_policy": POLICY,
            "provider": "scripted-sandbox-tests-v1",
            "system_prompt": TASK,
            "max_elapsed_seconds": 120,
            "max_steps": 3,
            "pricing": base.pricing.model_copy(update={"provider": "scripted-sandbox-tests-v1"}),
        }
    )


class SandboxProvider:
    async def generate(self, request: ModelRequest) -> ModelResponse:
        action: ToolAction | FinishAction
        if request.messages[-1].role == "tool":
            result = TestsResult.model_validate_json(request.messages[-1].content)
            action = FinishAction(
                action="finish",
                result=FinalResult(
                    summary="Sandbox test status: " + result.status + ".", artifacts=()
                ),
            )
        else:
            action = ToolAction(
                action="tool_call",
                tool_name=TEST_TOOL,
                arguments={},
                decision_summary="Run the pinned fixture tests in a disposable sandbox.",
            )
        return ModelResponse(
            model="fixture-v1",
            content=action.model_dump_json(),
            finish_reason="stop",
            latency_ms=0.0,
            usage=TokenUsage(input_tokens=10, output_tokens=5),
        )


async def submit_sandbox(
    sessions: async_sessionmaker[AsyncSession],
    image: str,
    *,
    socket: Path = Path("/var/run/docker.sock"),
) -> UUID:
    config = sandbox_configuration(BoundSandbox(image, socket=socket).identity)
    async with sessions.begin() as session:
        agents = AgentRepository(session)
        agent = await agents.create("Durable sandbox test demonstration")
        version = await agents.create_version(agent.id, config.model_dump(mode="json"))
        run = await RunRepository(session).create(version.id)
        await enroll(session, run.id, task=TASK, profile=SANDBOX_PROFILE)
        return run.id


async def work_sandbox_once(
    sessions: async_sessionmaker[AsyncSession],
    *,
    run_id: UUID,
    image: str | None = None,
    socket: Path = Path("/var/run/docker.sock"),
    allow_execute: bool = False,
) -> RuntimeState | None:
    claim = await claim_next(sessions, profile=SANDBOX_PROFILE, run_id=run_id)
    if claim is None:
        return None
    async with sessions() as session:
        run = await RunRepository(session).get(run_id)
        version = await AgentRepository(session).get_version(run.agent_version_id)
        pinned = RuntimeConfig.model_validate_json(version.configuration_json)
        if pinned.sandbox is None or sandbox_configuration(pinned.sandbox) != pinned:
            raise ConfigurationRejected("Not the fixed sandbox profile")
        interrupted = any(
            [
                await session.scalar(
                    select(table.id).where(table.run_id == run_id, table.status == "REQUESTED")
                )
                is not None
                for table in (ModelInvocationRow, ToolCallRow)
            ]
        )
    binding: BoundSandbox | None = None
    config = pinned
    operator = POLICY if allow_execute else ToolPolicy()
    if not interrupted:
        authorize_sandbox(pinned.tool_policy, operator)
        if image is None:
            raise ValueError("Clean execution requires a sandbox image")
        binding = BoundSandbox(image, socket=socket)
        config = sandbox_configuration(binding.identity)
    return await execute(
        run_id,
        claim.task,
        provider_name=config.provider,
        provider=SandboxProvider(),
        sandbox=binding,
        tool_policy=operator,
        store=PostgresExecutionStore(sessions, claim=claim, expected_config=config),
    )


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("submit", "work"))
    parser.add_argument("--run-id", type=UUID)
    parser.add_argument("--image")
    parser.add_argument("--socket", type=Path, default=Path("/var/run/docker.sock"))
    parser.add_argument("--allow-execute", action="store_true")
    args = parser.parse_args()
    if args.command == "submit" and (args.run_id or args.allow_execute or not args.image):
        parser.error("Submit requires --image and accepts no run ID or execution grant")
    if args.command == "work" and args.run_id is None:
        parser.error("Work requires --run-id")
    engine = create_engine(database_url())
    try:
        sessions = async_sessionmaker(engine)
        if args.command == "submit":
            run_id = await submit_sandbox(sessions, args.image, socket=args.socket)
            print(json.dumps({"run_id": str(run_id)}))
            return 0
        result = await work_sandbox_once(
            sessions,
            run_id=args.run_id,
            image=args.image,
            socket=args.socket,
            allow_execute=args.allow_execute,
        )
        print(
            json.dumps(
                {
                    "selected": result is not None,
                    "error_code": result.error_code if result else None,
                    "summary": result.final_result.summary
                    if result and result.final_result
                    else None,
                }
            )
        )
        return int(result is not None and result.error_code is not None)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    try:
        with telemetry():
            raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        raise SystemExit(130) from None
    except Exception:
        print("sandbox_worker_failed")
        raise SystemExit(1) from None
