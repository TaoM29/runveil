"""Short committed runtime boundaries backed by the existing repositories."""

import json
from typing import Literal
from uuid import UUID, uuid4

from pydantic import ValidationError
from runveil_core.agents import JsonValue
from runveil_core.errors import InvalidTransition
from runveil_core.models import Message
from runveil_core.runs import RunStatus
from runveil_core.runtime import Cursor, Pending, RuntimeConfig, RuntimeState, Started
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runveil_persistence.history import HistoryRepository
from runveil_persistence.invocations import InvocationRepository
from runveil_persistence.models import EventRow
from runveil_persistence.repositories import AgentRepository, RunRepository


class PostgresExecutionStore:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions

    async def start(self, run_id: UUID, task: str, provider: str) -> Started:
        async with self.sessions.begin() as session:
            runs = RunRepository(session)
            run = await runs.get(run_id)
            if run.status != RunStatus.QUEUED:
                raise InvalidTransition("Execution requires a queued run; resume is unsupported")
            version = await AgentRepository(session).get_version(run.agent_version_id)
            try:
                config = RuntimeConfig.model_validate_json(version.configuration_json)
                state = RuntimeState(
                    messages=(
                        Message(role="system", content=config.system_prompt),
                        Message(role="user", content=task),
                    )
                )
            except ValidationError:
                raise ValueError("Invalid runtime configuration or task") from None
            if config.provider != provider:
                raise ValueError("Provider binding does not match the pinned configuration")
            sequence = await session.scalar(
                select(func.max(EventRow.sequence)).where(EventRow.run_id == run_id)
            )
            run = await runs.transition(
                run_id,
                RunStatus.RUNNING,
                expected_revision=run.revision,
                expected_sequence=sequence or 0,
            )
            # The transition holds the run lock; its lifecycle event is now the tail.
            sequence = await session.scalar(
                select(func.max(EventRow.sequence)).where(EventRow.run_id == run_id)
            )
            checkpoint = await HistoryRepository(session).record_step(
                run_id,
                kind="runtime.started",
                details={},
                state=state.model_dump(mode="json"),
                expected_revision=run.revision,
                expected_sequence=sequence or 0,
            )
            return Started(Cursor(run_id, run.revision, checkpoint.event_sequence), config, state)

    async def request(
        self,
        cursor: Cursor,
        *,
        kind: Literal["model", "tool"],
        payload: dict[str, JsonValue],
        config: RuntimeConfig,
        model_invocation_id: UUID | None = None,
        tool_name: str | None = None,
    ) -> Pending:
        if (kind == "tool") != (tool_name is not None):
            raise ValueError("Only tool requests require a tool name")
        async with self.sessions.begin() as session:
            invocations = InvocationRepository(session)
            record_id = uuid4()
            if kind == "model":
                model = await invocations.request_model(
                    cursor.run_id,
                    invocation_id=record_id,
                    provider=config.provider,
                    model=config.model,
                    request=payload,
                    expected_revision=cursor.revision,
                    expected_sequence=cursor.sequence,
                )
                sequence = model.requested_event_sequence
            else:
                assert tool_name is not None
                tool = await invocations.request_tool(
                    cursor.run_id,
                    tool_call_id=record_id,
                    tool_name=tool_name,
                    arguments=payload,
                    model_invocation_id=model_invocation_id,
                    expected_revision=cursor.revision,
                    expected_sequence=cursor.sequence,
                )
                sequence = tool.requested_event_sequence
            return Pending(Cursor(cursor.run_id, cursor.revision, sequence), record_id, kind)

    async def complete(
        self,
        pending: Pending,
        state: RuntimeState,
        *,
        result: dict[str, JsonValue] | None = None,
        error_code: str | None = None,
    ) -> Cursor:
        cursor = pending.cursor
        async with self.sessions.begin() as session:
            invocations = InvocationRepository(session)
            complete = (
                invocations.complete_model if pending.kind == "model" else invocations.complete_tool
            )
            await complete(
                cursor.run_id,
                pending.id,
                state=state.model_dump(mode="json"),
                result=result,
                error_code=error_code,
                expected_revision=cursor.revision,
                expected_sequence=cursor.sequence,
            )
            checkpoint = await HistoryRepository(session).latest_checkpoint(cursor.run_id)
            assert checkpoint is not None
            cursor = Cursor(cursor.run_id, cursor.revision, checkpoint.event_sequence)
            if state.final_result is not None or state.error_code is not None:
                await RunRepository(session).transition(
                    cursor.run_id,
                    RunStatus.FAILED if state.error_code else RunStatus.SUCCEEDED,
                    expected_revision=cursor.revision,
                    expected_sequence=cursor.sequence,
                )
            return cursor

    async def exhaust(self, cursor: Cursor, state: RuntimeState) -> None:
        async with self.sessions.begin() as session:
            checkpoint = await HistoryRepository(session).record_step(
                cursor.run_id,
                kind="runtime.step_limit_exceeded",
                details={"max_steps": state.steps_used},
                state=state.model_dump(mode="json"),
                expected_revision=cursor.revision,
                expected_sequence=cursor.sequence,
            )
            await RunRepository(session).transition(
                cursor.run_id,
                RunStatus.FAILED,
                expected_revision=cursor.revision,
                expected_sequence=checkpoint.event_sequence,
            )


async def load_runtime_state(session: AsyncSession, run_id: UUID) -> RuntimeState | None:
    """Restore evidence, not execution. Read current lifecycle separately."""
    checkpoint = await HistoryRepository(session).latest_checkpoint(run_id)
    if checkpoint is None:
        return None
    return RuntimeState.model_validate_json(json.dumps(checkpoint.state))
