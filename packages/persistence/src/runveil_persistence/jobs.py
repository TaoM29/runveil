"""PostgreSQL work selection and transaction-local ownership fences."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from runveil_core.errors import InvalidTransition, NotFound
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runveil_persistence.models import JobRow, RunRow

LEASE_SECONDS = 660


class OwnershipLost(Exception):
    """The caller has no live ownership of this enrolled run."""


@dataclass(frozen=True)
class Claim:
    run_id: UUID
    token: UUID
    profile: str
    task: str


async def database_now(session: AsyncSession) -> datetime:
    at = await session.scalar(select(func.clock_timestamp()))
    if not isinstance(at, datetime):
        raise TypeError("Database clock did not return a datetime")
    return at


async def enroll(session: AsyncSession, run_id: UUID, *, task: str, profile: str) -> None:
    """Caller owns transaction. Repeated identical enrollment is a no-op."""
    if not 1 <= len(task) <= 16384 or not 1 <= len(profile) <= 100:
        raise ValueError("Invalid task or profile length")
    run = await session.scalar(select(RunRow).where(RunRow.id == run_id).with_for_update())
    if run is None:
        raise NotFound("Run not found")
    existing = await session.get(JobRow, run_id)
    if existing is not None:
        if existing.task != task or existing.profile != profile:
            raise ValueError("Enrollment does not match the existing job")
        return
    if run.status != "QUEUED":
        raise InvalidTransition("Enrollment requires a queued run")
    session.add(JobRow(run_id=run_id, task=task, profile=profile))
    await session.flush()


async def claim_next(
    sessions: async_sessionmaker[AsyncSession], *, profile: str, run_id: UUID | None = None
) -> Claim | None:
    async with sessions.begin() as session:
        now = await database_now(session)
        query = (
            select(RunRow)
            .join(JobRow, JobRow.run_id == RunRow.id)
            .where(
                RunRow.status.in_(("QUEUED", "RUNNING", "RETRYING")),
                or_(JobRow.available_at <= now, JobRow.deadline_at <= now),
                JobRow.profile == profile,
                JobRow.quarantined_at.is_(None),
                JobRow.admission_not_before <= now,
                or_(JobRow.token.is_(None), JobRow.expires_at <= now),
            )
            .order_by(RunRow.created_at, RunRow.id)
            .limit(1)
            .with_for_update(of=RunRow, skip_locked=True)
        )
        if run_id is not None:
            query = query.where(RunRow.id == run_id)
        run = await session.scalar(query)
        if run is None:
            return None
        job = await session.get(JobRow, run.id, with_for_update=True)
        assert job is not None
        now = await database_now(session)
        # Recheck after acquiring locks: another claimant may just have renewed.
        expired = job.deadline_at is not None and job.deadline_at <= now
        if job.quarantined_at is not None or job.admission_not_before > now:
            return None
        if (job.available_at > now and not expired) or (
            job.expires_at is not None and job.expires_at > now
        ):
            return None
        job.token = uuid4()
        job.expires_at = now + timedelta(seconds=LEASE_SECONDS)
        await session.flush()
        return Claim(run.id, job.token, job.profile, job.task)


async def fence(session: AsyncSession, run_id: UUID, claim: Claim | None) -> None:
    """Lock in run/job order; the fence and execution write share a transaction."""
    run = await session.scalar(select(RunRow).where(RunRow.id == run_id).with_for_update())
    if run is None:
        raise NotFound("Run not found")
    job = await session.get(JobRow, run_id, with_for_update=True)
    if job is None and claim is None:
        return
    now = await database_now(session)
    if (
        job is None
        or claim is None
        or claim.run_id != run_id
        or job.token != claim.token
        or job.profile != claim.profile
        or job.task != claim.task
        or job.quarantined_at is not None
        or job.expires_at is None
        or job.expires_at <= now
    ):
        raise OwnershipLost("Worker ownership is absent, expired or superseded")
    job.expires_at = now + timedelta(seconds=LEASE_SECONDS)
    await session.flush()
