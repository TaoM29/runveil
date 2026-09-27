"""Short committed runtime boundaries backed by the existing repositories."""

import json
from typing import Literal
from uuid import UUID, uuid4

from pydantic import ValidationError
from runveil_core.agents import JsonValue
from runveil_core.errors import InvalidTransition
from runveil_core.models import Message, ModelRequest, ModelResponse, validate_response
from runveil_core.runs import RunStatus
from runveil_core.runtime import Cursor, Pending, RuntimeConfig, RuntimeState, Started
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runveil_persistence.history import HistoryRepository
from runveil_persistence.invocations import InvocationRepository
from runveil_persistence.jobs import Claim, fence
from runveil_persistence.models import EventRow, ModelInvocationRow, ToolCallRow
from runveil_persistence.repositories import AgentRepository, RunRepository


class PostgresExecutionStore:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        *,
        claim: Claim | None = None,
        expected_config: RuntimeConfig | None = None,
    ) -> None:
        self.sessions = sessions
        self.claim = claim
        self.expected_config = expected_config

    async def start(self, run_id: UUID, task: str, provider: str) -> Started:
        async with self.sessions.begin() as session:
            await fence(session, run_id, self.claim)
            runs = RunRepository(session)
            run = await runs.get(run_id)
            if run.status != RunStatus.QUEUED and not (
                self.claim is not None and run.status == RunStatus.RUNNING
            ):
                raise InvalidTransition("Execution requires a queued run or claimed recovery")
            if self.claim is not None and task != self.claim.task:
                raise ValueError("Task does not match enrollment")
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
            if self.expected_config is not None and config != self.expected_config:
                raise ValueError("Runtime configuration does not match worker profile")
            if run.status == RunStatus.RUNNING:
                return await self._resume(session, run_id, run.revision, config)
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

    async def _resume(
        self, session: AsyncSession, run_id: UUID, revision: int, config: RuntimeConfig
    ) -> Started:
        checkpoint = await HistoryRepository(session).latest_checkpoint(run_id)
        if checkpoint is None or checkpoint.run_revision != revision:
            raise ValueError("Recovery requires a checkpoint at the current revision")
        state = RuntimeState.model_validate_json(json.dumps(checkpoint.state))
        if (
            state.schema_version != 2
            or state.final_result is not None
            or state.error_code is not None
            or state.steps_used > config.max_steps
            or (state.next_tool is None) != (state.source_model_id is None)
        ):
            raise ValueError("Checkpoint is not resumable")
        if state.next_tool is not None:
            source = await session.get(ModelInvocationRow, state.source_model_id)
            if (
                source is None
                or source.run_id != run_id
                or source.status != "SUCCEEDED"
                or source.result is None
                or source.step_number != checkpoint.step_number
            ):
                raise ValueError("Invalid checkpoint tool provenance")
            action = validate_response(
                ModelRequest.model_validate_json(json.dumps(source.request)),
                ModelResponse.model_validate_json(json.dumps(source.result)),
            )
            if action != state.next_tool:
                raise ValueError("Checkpoint action differs from its committed model outcome")
        sequence = await session.scalar(
            select(func.max(EventRow.sequence)).where(EventRow.run_id == run_id)
        )
        cursor = Cursor(run_id, revision, sequence or 0)
        outstanding: list[Pending] = []
        completed_count = 0
        tables: tuple[
            tuple[type[ModelInvocationRow] | type[ToolCallRow], Literal["model", "tool"]], ...
        ] = (
            (ModelInvocationRow, "model"),
            (ToolCallRow, "tool"),
        )
        for table, kind in tables:
            completed_count += (
                await session.scalar(
                    select(func.count())
                    .select_from(table)
                    .where(table.run_id == run_id, table.status != "REQUESTED")
                )
                or 0
            )
            records = await session.scalars(
                select(table).where(table.run_id == run_id, table.status == "REQUESTED").limit(2)
            )
            for record in records:
                assert isinstance(record, (ModelInvocationRow, ToolCallRow))
                if record.requested_event_sequence != checkpoint.event_sequence + 1:
                    raise ValueError("Unexpected history after checkpoint")
                outstanding.append(Pending(cursor, record.id, kind))
        if completed_count != state.steps_used:
            raise ValueError("Checkpoint invocation count differs from history")
        if outstanding:
            if (
                len(outstanding) != 1
                or cursor.sequence != checkpoint.event_sequence + 1
                or state.steps_used >= config.max_steps
            ):
                raise ValueError("Ambiguous interrupted execution history")
            return Started(cursor, config, state, outstanding[0])
        if cursor.sequence != checkpoint.event_sequence:
            raise ValueError("Unexpected history after checkpoint")
        return Started(cursor, config, state)

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
            await fence(session, cursor.run_id, self.claim)
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
            await fence(session, cursor.run_id, self.claim)
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
            await fence(session, cursor.run_id, self.claim)
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
