"""Durable invocation records; no external calls or implicit commits."""

import json
from uuid import UUID

from runveil_core.agents import JsonValue, configuration_json
from runveil_core.errors import InvalidTransition, NotFound
from runveil_core.invocations import (
    InvocationStatus,
    ModelInvocation,
    ToolCall,
    validate_label,
    validate_outcome,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from runveil_persistence.history import HistoryRepository, lock_running_run
from runveil_persistence.models import EventRow, ModelInvocationRow, ToolCallRow


def model_snapshot(row: ModelInvocationRow) -> ModelInvocation:
    return ModelInvocation(
        id=row.id,
        run_id=row.run_id,
        requested_event_sequence=row.requested_event_sequence,
        completed_event_sequence=row.completed_event_sequence,
        step_number=row.step_number,
        error_code=row.error_code,
        requested_at=row.requested_at,
        completed_at=row.completed_at,
        provider=row.provider,
        model=row.model,
        status=InvocationStatus(row.status),
        request_json=configuration_json(row.request),
        result_json=None if row.result is None else configuration_json(row.result),
    )


def tool_snapshot(row: ToolCallRow) -> ToolCall:
    return ToolCall(
        id=row.id,
        run_id=row.run_id,
        requested_event_sequence=row.requested_event_sequence,
        completed_event_sequence=row.completed_event_sequence,
        step_number=row.step_number,
        error_code=row.error_code,
        requested_at=row.requested_at,
        completed_at=row.completed_at,
        tool_name=row.tool_name,
        model_invocation_id=row.model_invocation_id,
        status=InvocationStatus(row.status),
        request_json=configuration_json(row.request),
        result_json=None if row.result is None else configuration_json(row.result),
    )


class InvocationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def request_model(
        self,
        run_id: UUID,
        *,
        invocation_id: UUID,
        provider: str,
        model: str,
        request: dict[str, JsonValue],
        retry_of: UUID | None = None,
        expected_revision: int,
        expected_sequence: int,
    ) -> ModelInvocation:
        validate_label(provider)
        validate_label(model)
        row = ModelInvocationRow(
            id=invocation_id,
            run_id=run_id,
            provider=provider,
            model=model,
            request=json.loads(configuration_json(request)),
        )
        await self._request(row, expected_revision, expected_sequence, retry_of=retry_of)
        return model_snapshot(row)

    async def request_tool(
        self,
        run_id: UUID,
        *,
        tool_call_id: UUID,
        tool_name: str,
        arguments: dict[str, JsonValue],
        model_invocation_id: UUID | None = None,
        expected_revision: int,
        expected_sequence: int,
    ) -> ToolCall:
        validate_label(tool_name)
        row = ToolCallRow(
            id=tool_call_id,
            run_id=run_id,
            tool_name=tool_name,
            model_invocation_id=model_invocation_id,
            request=json.loads(configuration_json(arguments)),
        )
        await self._request(row, expected_revision, expected_sequence)
        return tool_snapshot(row)

    async def _request(
        self,
        row: ModelInvocationRow | ToolCallRow,
        revision: int,
        sequence: int,
        *,
        retry_of: UUID | None = None,
    ) -> None:
        run = await lock_running_run(
            self.session,
            row.run_id,
            expected_revision=revision,
            expected_sequence=sequence,
        )
        if isinstance(row, ToolCallRow) and row.model_invocation_id is not None:
            source = await self.session.get(
                ModelInvocationRow, row.model_invocation_id, populate_existing=True
            )
            if source is None or source.run_id != row.run_id:
                raise NotFound("Source model invocation not found in this run")
            if source.status != InvocationStatus.SUCCEEDED:
                raise InvalidTransition("Tool source must be a succeeded model invocation")
        payload: dict[str, JsonValue] = {"record_id": str(row.id)}
        if retry_of is not None:
            source = await self.session.get(ModelInvocationRow, retry_of)
            if (
                not isinstance(row, ModelInvocationRow)
                or source is None
                or source.run_id != row.run_id
                or source.status != InvocationStatus.FAILED
                or source.error_code != "provider_rate_limited"
                or source.request != row.request
                or source.provider != row.provider
                or source.model != row.model
            ):
                raise ValueError("Retry must repeat a known failed model request in this run")
            payload["retry_of"] = str(retry_of)
        prefix = "model" if isinstance(row, ModelInvocationRow) else "tool"
        event = EventRow(
            run_id=row.run_id,
            kind=f"{prefix}.requested",
            run_revision=run.revision,
            payload=payload,
        )
        self.session.add(event)
        await self.session.flush()
        row.requested_event_sequence = event.sequence
        row.requested_at = event.created_at
        self.session.add(row)
        await self.session.flush()

    async def get_model(self, run_id: UUID, invocation_id: UUID) -> ModelInvocation:
        row = await self.session.get(ModelInvocationRow, invocation_id, populate_existing=True)
        if row is None or row.run_id != run_id:
            raise NotFound("Model invocation not found in this run")
        return model_snapshot(row)

    async def get_tool(self, run_id: UUID, tool_call_id: UUID) -> ToolCall:
        row = await self.session.get(ToolCallRow, tool_call_id, populate_existing=True)
        if row is None or row.run_id != run_id:
            raise NotFound("Tool call not found in this run")
        return tool_snapshot(row)

    async def complete_model(
        self,
        run_id: UUID,
        invocation_id: UUID,
        *,
        state: dict[str, JsonValue],
        expected_revision: int,
        expected_sequence: int,
        result: dict[str, JsonValue] | None = None,
        error_code: str | None = None,
    ) -> ModelInvocation:
        row = await self._complete(
            ModelInvocationRow,
            run_id,
            invocation_id,
            state,
            expected_revision,
            expected_sequence,
            result,
            error_code,
        )
        assert isinstance(row, ModelInvocationRow)
        return model_snapshot(row)

    async def complete_tool(
        self,
        run_id: UUID,
        tool_call_id: UUID,
        *,
        state: dict[str, JsonValue],
        expected_revision: int,
        expected_sequence: int,
        result: dict[str, JsonValue] | None = None,
        error_code: str | None = None,
    ) -> ToolCall:
        row = await self._complete(
            ToolCallRow,
            run_id,
            tool_call_id,
            state,
            expected_revision,
            expected_sequence,
            result,
            error_code,
        )
        assert isinstance(row, ToolCallRow)
        return tool_snapshot(row)

    async def _complete(
        self,
        table: type[ModelInvocationRow] | type[ToolCallRow],
        run_id: UUID,
        record_id: UUID,
        state: dict[str, JsonValue],
        revision: int,
        sequence: int,
        result: dict[str, JsonValue] | None,
        error_code: str | None,
    ) -> ModelInvocationRow | ToolCallRow:
        validate_outcome(result, error_code)
        state_copy: dict[str, JsonValue] = json.loads(configuration_json(state))
        result_copy = None if result is None else json.loads(configuration_json(result))
        run = await lock_running_run(
            self.session,
            run_id,
            expected_revision=revision,
            expected_sequence=sequence,
        )
        row = await self.session.scalar(
            select(table)
            .where(table.id == record_id, table.run_id == run_id)
            .execution_options(populate_existing=True)
        )
        if row is None:
            raise NotFound("Invocation record not found in this run")
        assert isinstance(row, (ModelInvocationRow, ToolCallRow))
        if row.status != InvocationStatus.REQUESTED:
            raise InvalidTransition("Invocation outcome is already recorded")
        prefix = "model" if isinstance(row, ModelInvocationRow) else "tool"
        event_kind = f"{prefix}.completed" if result is not None else f"{prefix}.failed"
        event = EventRow(
            run_id=run_id,
            kind=event_kind,
            run_revision=run.revision,
            payload={"record_id": str(record_id)},
        )
        self.session.add(event)
        await self.session.flush()
        checkpoint = await HistoryRepository(self.session).record_step(
            run_id,
            kind=event_kind,
            details={"record_id": str(record_id)},
            state=state_copy,
            expected_revision=revision,
            expected_sequence=event.sequence,
        )
        row.status = InvocationStatus.SUCCEEDED if result is not None else InvocationStatus.FAILED
        row.result = result_copy
        row.error_code = error_code
        row.step_number = checkpoint.step_number
        row.completed_event_sequence = event.sequence
        row.completed_at = event.created_at
        await self.session.flush()
        return row
