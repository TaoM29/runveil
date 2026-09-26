"""Ordered history. Each write is one caller-owned database transaction."""

import json
from uuid import UUID

from runveil_core.agents import JsonValue, configuration_json
from runveil_core.errors import InvalidTransition, NotFound, RevisionConflict
from runveil_core.history import Checkpoint, ExecutionEvent, RunStep, validate_step_kind
from runveil_core.runs import RunStatus
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from runveil_persistence.models import CheckpointRow, EventRow, RunRow, StepRow
from runveil_persistence.repositories import RunRepository


def checkpoint_snapshot(row: CheckpointRow) -> Checkpoint:
    return Checkpoint(
        row.run_id,
        row.event_sequence,
        row.step_number,
        row.run_revision,
        RunStatus(row.run_status),
        row.schema_version,
        configuration_json(row.state),
        row.created_at,
    )


class HistoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def record_step(
        self,
        run_id: UUID,
        *,
        kind: str,
        details: dict[str, JsonValue],
        state: dict[str, JsonValue],
        expected_revision: int,
        expected_sequence: int,
    ) -> Checkpoint:
        """Atomically record a boundary, its events and a full checkpoint.

        The caller must roll back on failure. No external work belongs inside this
        transaction. The checkpoint's event position is the next write's cursor.
        """
        validate_step_kind(kind)
        # Validate and detach untrusted JSON before acquiring a database lock.
        details_copy = json.loads(configuration_json(details))
        state_copy = json.loads(configuration_json(state))
        row = await self.session.scalar(
            select(RunRow)
            .where(RunRow.id == run_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if row is None:
            raise NotFound("Run not found")
        sequence = await self.session.scalar(
            select(func.max(EventRow.sequence)).where(EventRow.run_id == run_id)
        )
        if row.revision != expected_revision or (sequence or 0) != expected_sequence:
            raise RevisionConflict("Run history changed; reload before recording a boundary")
        if row.status != RunStatus.RUNNING:
            raise InvalidTransition("Execution boundaries require a running run")
        latest_step = await self.session.scalar(
            select(func.max(StepRow.number)).where(StepRow.run_id == run_id)
        )
        step_number = (latest_step or 0) + 1
        step = StepRow(run_id=run_id, number=step_number, kind=kind, details=details_copy)
        self.session.add(step)
        await self.session.flush()
        for event_kind in ("step.recorded", "checkpoint.created"):
            event = EventRow(
                run_id=run_id,
                kind=event_kind,
                run_revision=row.revision,
                step_number=step_number,
                payload={},
            )
            self.session.add(event)
            await self.session.flush()
        checkpoint = CheckpointRow(
            run_id=run_id,
            event_sequence=event.sequence,
            step_number=step_number,
            run_revision=row.revision,
            run_status=row.status,
            schema_version=1,
            state=state_copy,
        )
        self.session.add(checkpoint)
        await self.session.flush()
        return checkpoint_snapshot(checkpoint)

    async def events(
        self, run_id: UUID, *, after_sequence: int = 0, limit: int = 100
    ) -> list[ExecutionEvent]:
        if after_sequence < 0 or not 1 <= limit <= 1000:
            raise ValueError("Invalid event cursor or limit (1–1000)")
        await RunRepository(self.session).get(run_id)
        rows = await self.session.scalars(
            select(EventRow)
            .where(EventRow.run_id == run_id, EventRow.sequence > after_sequence)
            .order_by(EventRow.sequence)
            .limit(limit)
        )
        return [
            ExecutionEvent(
                row.run_id,
                row.sequence,
                row.kind,
                row.run_revision,
                row.step_number,
                configuration_json(row.payload),
                row.created_at,
            )
            for row in rows
        ]

    async def steps(
        self, run_id: UUID, *, after_number: int = 0, limit: int = 100
    ) -> list[RunStep]:
        if after_number < 0 or not 1 <= limit <= 1000:
            raise ValueError("Invalid step cursor or limit (1–1000)")
        await RunRepository(self.session).get(run_id)
        rows = await self.session.scalars(
            select(StepRow)
            .where(StepRow.run_id == run_id, StepRow.number > after_number)
            .order_by(StepRow.number)
            .limit(limit)
        )
        return [
            RunStep(
                row.run_id, row.number, row.kind, configuration_json(row.details), row.created_at
            )
            for row in rows
        ]

    async def latest_checkpoint(self, run_id: UUID) -> Checkpoint | None:
        """Load persisted state, rejecting unsupported versions; never execute it.

        Its run revision may precede the current lifecycle revision. Read events
        after its watermark before deciding how to resume in a future runtime.
        """
        await RunRepository(self.session).get(run_id)
        row = await self.session.scalar(
            select(CheckpointRow)
            .where(CheckpointRow.run_id == run_id)
            .order_by(CheckpointRow.event_sequence.desc())
            .limit(1)
        )
        return None if row is None else checkpoint_snapshot(row)
