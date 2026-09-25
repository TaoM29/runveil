"""Concrete repositories. Callers own the session's transaction boundary."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from runveil_core.agents import AgentDefinition, AgentVersion, JsonValue, configuration_json
from runveil_core.errors import NotFound, RevisionConflict
from runveil_core.runs import Run, RunStatus
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from runveil_persistence.models import AgentRow, RunRow, VersionRow


def version_snapshot(row: VersionRow) -> AgentVersion:
    return AgentVersion(
        row.id, row.agent_id, row.number, configuration_json(row.configuration), row.created_at
    )


def run_snapshot(row: RunRow) -> Run:
    return Run(
        row.id,
        row.agent_version_id,
        RunStatus(row.status),
        row.revision,
        row.created_at,
        row.state_changed_at,
        row.started_at,
        row.finished_at,
    )


class AgentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, name: str) -> AgentDefinition:
        # Validate before issuing SQL; authoritative creation time comes from PostgreSQL.
        definition = AgentDefinition(uuid4(), name, datetime.now(UTC))
        row = AgentRow(id=definition.id, name=definition.name)
        self.session.add(row)
        await self.session.flush()
        return AgentDefinition(row.id, row.name, row.created_at)

    async def get(self, agent_id: UUID) -> AgentDefinition:
        row = await self.session.get(AgentRow, agent_id)
        if row is None:
            raise NotFound("Agent definition not found")
        return AgentDefinition(row.id, row.name, row.created_at)

    async def create_version(
        self, agent_id: UUID, configuration: dict[str, JsonValue]
    ) -> AgentVersion:
        encoded = configuration_json(configuration)
        parent = await self.session.scalar(
            select(AgentRow.id).where(AgentRow.id == agent_id).with_for_update()
        )
        if parent is None:
            raise NotFound("Agent definition not found")
        latest = await self.session.scalar(
            select(func.max(VersionRow.number)).where(VersionRow.agent_id == agent_id)
        )
        snapshot = AgentVersion(uuid4(), agent_id, (latest or 0) + 1, encoded, datetime.now(UTC))
        row = VersionRow(
            id=snapshot.id,
            agent_id=agent_id,
            number=snapshot.number,
            configuration=snapshot.configuration,
        )
        self.session.add(row)
        await self.session.flush()
        return version_snapshot(row)

    async def get_version(self, version_id: UUID) -> AgentVersion:
        row = await self.session.get(VersionRow, version_id)
        if row is None:
            raise NotFound("Agent version not found")
        return version_snapshot(row)


class RunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, agent_version_id: UUID) -> Run:
        if await self.session.get(VersionRow, agent_version_id) is None:
            raise NotFound("Agent version not found")
        row = RunRow(id=uuid4(), agent_version_id=agent_version_id)
        self.session.add(row)
        await self.session.flush()
        return run_snapshot(row)

    async def get(self, run_id: UUID) -> Run:
        row = await self.session.get(RunRow, run_id, populate_existing=True)
        if row is None:
            raise NotFound("Run not found")
        return run_snapshot(row)

    async def transition(self, run_id: UUID, target: RunStatus, *, expected_revision: int) -> Run:
        row = await self.session.scalar(
            select(RunRow)
            .where(RunRow.id == run_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if row is None:
            raise NotFound("Run not found")
        if row.revision != expected_revision:
            raise RevisionConflict("Run changed; reload it before requesting a transition")
        at = await self.session.scalar(select(func.clock_timestamp()))
        if not isinstance(at, datetime):
            raise TypeError("Database clock did not return a datetime")
        updated = run_snapshot(row).transition(target, at=at)
        row.status = updated.status.value
        row.revision = updated.revision
        row.state_changed_at = updated.state_changed_at
        row.started_at = updated.started_at
        row.finished_at = updated.finished_at
        await self.session.flush()
        return run_snapshot(row)
