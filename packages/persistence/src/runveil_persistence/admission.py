"""Admission scheduling state and audit, without changing runtime history."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from pydantic import ValidationError
from runveil_core.errors import InvalidTransition, NotFound, RevisionConflict
from runveil_core.runtime import RuntimeConfig
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runveil_persistence.jobs import Claim, OwnershipLost, database_now, fence
from runveil_persistence.models import AdmissionEventRow, JobRow, RunRow
from runveil_persistence.repositories import AgentRepository

REJECTION_LIMIT = 3
COOLDOWN_SECONDS = 30
ACTIVE = ("QUEUED", "RUNNING", "RETRYING")


@dataclass(frozen=True)
class AdmissionStatus:
    run_id: UUID
    run_status: str
    profile: str
    failures: int
    revision: int
    not_before: datetime
    quarantined_at: datetime | None


def snapshot(run: RunRow, job: JobRow) -> AdmissionStatus:
    return AdmissionStatus(
        run.id,
        run.status,
        job.profile,
        job.admission_failures,
        job.admission_revision,
        job.admission_not_before,
        job.quarantined_at,
    )


async def inspect_admission(
    sessions: async_sessionmaker[AsyncSession], run_id: UUID
) -> AdmissionStatus:
    async with sessions() as session:
        row = (
            await session.execute(
                select(RunRow, JobRow)
                .join(JobRow, JobRow.run_id == RunRow.id)
                .where(RunRow.id == run_id)
            )
        ).one_or_none()
        if row is None:
            raise NotFound("Enrolled run not found")
        return snapshot(row[0], row[1])


def audit(session: AsyncSession, job: JobRow, action: str) -> None:
    session.add(
        AdmissionEventRow(
            run_id=job.run_id,
            revision=job.admission_revision,
            action=action,
            failures=job.admission_failures,
        )
    )


async def record_configuration_rejection(
    sessions: async_sessionmaker[AsyncSession], claim: Claim
) -> None:
    async with sessions.begin() as session:
        await fence(session, claim.run_id, claim)
        run = await session.get(RunRow, claim.run_id)
        job = await session.get(JobRow, claim.run_id)
        assert run is not None and job is not None
        if run.status not in ACTIVE:
            raise InvalidTransition("Admission failure requires a nonterminal executable run")
        now = await database_now(session)
        job.admission_failures += 1
        job.admission_revision += 1
        job.admission_not_before = now + timedelta(seconds=COOLDOWN_SECONDS)
        if job.admission_failures == REJECTION_LIMIT:
            job.quarantined_at = now
        job.token = None
        job.expires_at = None
        audit(session, job, "rejected")


async def release_quarantine(
    sessions: async_sessionmaker[AsyncSession],
    run_id: UUID,
    *,
    expected_revision: int,
    profile: str,
    expected_config: RuntimeConfig,
) -> AdmissionStatus:
    async with sessions.begin() as session:
        run = await session.scalar(select(RunRow).where(RunRow.id == run_id).with_for_update())
        job = await session.get(JobRow, run_id, with_for_update=True)
        if run is None or job is None:
            raise NotFound("Enrolled run not found")
        if job.admission_revision != expected_revision:
            raise RevisionConflict("Admission revision changed")
        if run.status not in ACTIVE or job.quarantined_at is None:
            raise InvalidTransition("Release requires a quarantined nonterminal executable run")
        now = await database_now(session)
        if job.expires_at is not None and job.expires_at > now:
            raise OwnershipLost("Cannot release a live owner")
        version = await AgentRepository(session).get_version(run.agent_version_id)
        try:
            config = RuntimeConfig.model_validate_json(version.configuration_json)
        except ValidationError:
            raise ValueError("Pinned configuration is invalid") from None
        if job.profile != profile or config != expected_config:
            raise ValueError("Repair binding does not match the pinned configuration")
        job.admission_failures = 0
        job.admission_revision += 1
        job.admission_not_before = now
        job.quarantined_at = None
        job.token = None
        job.expires_at = None
        audit(session, job, "released")
        await session.flush()
        return snapshot(run, job)
