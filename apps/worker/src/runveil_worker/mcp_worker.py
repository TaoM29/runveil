"""One pinned local read-only MCP fixture, selected explicitly by run ID."""

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
from uuid import UUID

from runveil_core.mcp import MCP_POLICY, MCP_PROFILE, MCP_TOOL, McpIdentity
from runveil_core.models import (
    FinalResult,
    FinishAction,
    ModelRequest,
    ModelResponse,
    TokenUsage,
    ToolAction,
)
from runveil_core.runtime import RuntimeConfig, RuntimeState, execute
from runveil_core.tools import ToolError, ToolErrorCode, ToolPolicy, ToolRegistry
from runveil_persistence.database import create_engine, database_url
from runveil_persistence.execution import ConfigurationRejected, PostgresExecutionStore
from runveil_persistence.history import lock_running_run
from runveil_persistence.jobs import claim_next, database_now, enroll, fence
from runveil_persistence.models import JobRow, ModelInvocationRow, ToolCallRow
from runveil_persistence.repositories import AgentRepository, RunRepository
from runveil_tools.mcp_execution import PinnedMcpFixture
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runveil_worker.telemetry import telemetry
from runveil_worker.worker import CALLS_PROFILE, configuration

TASK = "Read the fixed public MCP fixture and report its identity."
_WORKER_DIGEST = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def mcp_configuration(identity: McpIdentity) -> RuntimeConfig:
    base = configuration(CALLS_PROFILE)
    assert base.pricing is not None
    return RuntimeConfig.model_validate(
        base.model_dump()
        | {
            "schema_version": 17,
            "mcp": identity,
            "tool_policy": MCP_POLICY,
            "provider": "scripted-mcp-fixture-v1",
            "system_prompt": TASK,
            "max_steps": 3,
            "max_elapsed_seconds": 3600,
            "pricing": base.pricing.model_copy(update={"provider": "scripted-mcp-fixture-v1"}),
        }
    )


def bound_configuration(binding: PinnedMcpFixture) -> RuntimeConfig:
    identity = binding.identity.model_copy(
        update={
            "implementation_digest": hashlib.sha256(
                (binding.identity.implementation_digest + _WORKER_DIGEST).encode()
            ).hexdigest()
        }
    )
    return mcp_configuration(identity)


class McpProvider:
    async def generate(self, request: ModelRequest) -> ModelResponse:
        action: ToolAction | FinishAction
        if request.messages[-1].role == "tool":
            action = FinishAction(
                action="finish",
                result=FinalResult(summary="Public MCP fixture verified.", artifacts=()),
            )
        else:
            action = ToolAction(
                action="tool_call",
                tool_name=MCP_TOOL,
                arguments={},
                decision_summary="Read the pinned public MCP fixture.",
            )
        return ModelResponse(
            model="fixture-v1",
            content=action.model_dump_json(),
            finish_reason="stop",
            latency_ms=0.0,
            usage=TokenUsage(input_tokens=10, output_tokens=5),
        )


async def submit_mcp(sessions: async_sessionmaker[AsyncSession]) -> UUID:
    config = bound_configuration(await asyncio.to_thread(PinnedMcpFixture))
    async with sessions.begin() as session:
        agents = AgentRepository(session)
        agent = await agents.create("Pinned MCP read demonstration")
        version = await agents.create_version(agent.id, config.model_dump(mode="json"))
        run = await RunRepository(session).create(version.id)
        await enroll(session, run.id, task=TASK, profile=MCP_PROFILE)
        return run.id


async def work_mcp_once(
    sessions: async_sessionmaker[AsyncSession], *, run_id: UUID, allow_read: bool = False
) -> RuntimeState | None:
    claim = await claim_next(sessions, profile=MCP_PROFILE, run_id=run_id)
    if claim is None:
        return None
    async with sessions() as session:
        run = await RunRepository(session).get(run_id)
        version = await AgentRepository(session).get_version(run.agent_version_id)
        pinned = RuntimeConfig.model_validate_json(version.configuration_json)
        if pinned.mcp is None or pinned != mcp_configuration(pinned.mcp) or claim.task != TASK:
            raise ConfigurationRejected("Not the fixed MCP profile")
        interrupted = any(
            [
                await session.scalar(
                    select(table.id).where(table.run_id == run_id, table.status == "REQUESTED")
                )
                is not None
                for table in (ModelInvocationRow, ToolCallRow)
            ]
        )
    binding = None
    config = pinned
    operator = MCP_POLICY if allow_read else ToolPolicy()
    if not interrupted:
        if operator != MCP_POLICY:
            raise ToolError(ToolErrorCode.DENIED)
        binding = await asyncio.to_thread(PinnedMcpFixture)
        config = bound_configuration(binding)

    async def admit() -> None:
        async with sessions.begin() as session:
            await fence(session, run_id, claim)
            call = (
                await session.scalars(
                    select(ToolCallRow).where(
                        ToolCallRow.run_id == run_id, ToolCallRow.status == "REQUESTED"
                    )
                )
            ).one()
            if call.tool_name != MCP_TOOL or call.request != {}:
                raise ToolError(ToolErrorCode.DENIED)
            current = await RunRepository(session).get(run_id)
            await lock_running_run(
                session,
                run_id,
                expected_revision=current.revision,
                expected_sequence=call.requested_event_sequence,
            )
            job = await session.get(JobRow, run_id)
            assert job is not None and job.deadline_at is not None
            if job.deadline_at <= await database_now(session):
                # Let core's next remaining-time boundary commit expiry atomically.
                raise ToolError(ToolErrorCode.TIMEOUT)

    return await execute(
        run_id,
        claim.task,
        provider_name=config.provider,
        provider=McpProvider(),
        tools=ToolRegistry([binding.binding(admit)]) if binding else None,
        tool_policy=operator,
        store=PostgresExecutionStore(sessions, claim=claim, expected_config=config),
    )


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("submit", "work"))
    parser.add_argument("--run-id", type=UUID)
    parser.add_argument("--allow-read", action="store_true")
    args = parser.parse_args()
    if args.command == "submit" and (args.run_id or args.allow_read):
        parser.error("Submission accepts no run ID or execution grant")
    if args.command == "work" and args.run_id is None:
        parser.error("Work requires --run-id")
    engine = create_engine(database_url())
    try:
        sessions = async_sessionmaker(engine)
        if args.command == "submit":
            print(json.dumps({"run_id": str(await submit_mcp(sessions))}))
            return 0
        state = await work_mcp_once(sessions, run_id=args.run_id, allow_read=args.allow_read)
        print(
            json.dumps(
                {
                    "selected": state is not None,
                    "error_code": state.error_code if state else None,
                    "summary": state.final_result.summary if state and state.final_result else None,
                }
            )
        )
        return int(state is not None and state.error_code is not None)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    try:
        with telemetry():
            raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        raise SystemExit(130) from None
    except Exception:
        print("mcp_worker_failed")
        raise SystemExit(1) from None
