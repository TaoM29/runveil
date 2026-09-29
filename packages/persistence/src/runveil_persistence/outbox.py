"""Recurring delivery hints, separate from execution ownership and history."""

from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID, uuid4

from runveil_core.errors import InvalidTransition
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runveil_persistence.jobs import OwnershipLost, database_now
from runveil_persistence.models import JobRow, OutboxRow, RunRow

PUBLICATION_LEASE_SECONDS = 60
REPUBLISH_SECONDS = 30
TERMINAL = ("SUCCEEDED", "FAILED", "CANCELLED")


@dataclass(frozen=True)
class Publication:
    run_id: UUID
    token: UUID


async def enroll_notification(session: AsyncSession, run_id: UUID, queue_url: str) -> None:
    """Caller owns the run/job/enrollment transaction; no broker I/O."""
    if not 1 <= len(queue_url) <= 2048:
        raise ValueError("Invalid queue URL length")
    run = await session.scalar(select(RunRow).where(RunRow.id == run_id).with_for_update())
    existing = await session.get(OutboxRow, run_id)
    if existing is not None:
        if existing.queue_url != queue_url:
            raise ValueError("Outbox destination does not match")
        return
    if run is None or run.status != "QUEUED":
        raise InvalidTransition("Outbox enrollment requires a queued run")
    session.add(OutboxRow(run_id=run_id, queue_url=queue_url))
    await session.flush()


async def claim_publication(
    sessions: async_sessionmaker[AsyncSession], *, queue_url: str, profile: str
) -> Publication | None:
    async with sessions.begin() as session:
        now = await database_now(session)
        row = await session.scalar(
            select(OutboxRow)
            .join(JobRow, JobRow.run_id == OutboxRow.run_id)
            .join(RunRow, RunRow.id == OutboxRow.run_id)
            .where(
                OutboxRow.queue_url == queue_url,
                JobRow.profile == profile,
                JobRow.quarantined_at.is_(None),
                JobRow.admission_not_before <= now,
                RunRow.status.in_(("QUEUED", "RUNNING", "RETRYING")),
                or_(JobRow.available_at <= now, JobRow.deadline_at <= now),
                or_(JobRow.token.is_(None), JobRow.expires_at <= now),
                OutboxRow.next_publish_at <= now,
                or_(OutboxRow.token.is_(None), OutboxRow.expires_at <= now),
            )
            .order_by(OutboxRow.next_publish_at, OutboxRow.run_id)
            .limit(1)
            .with_for_update(of=OutboxRow, skip_locked=True)
        )
        if row is None:
            return None
        row.token = uuid4()
        row.expires_at = await database_now(session) + timedelta(seconds=PUBLICATION_LEASE_SECONDS)
        await session.flush()
        return Publication(row.run_id, row.token)


async def published(sessions: async_sessionmaker[AsyncSession], claim: Publication) -> None:
    async with sessions.begin() as session:
        row = await session.get(OutboxRow, claim.run_id, with_for_update=True)
        now = await database_now(session)
        if (
            row is None
            or row.token != claim.token
            or row.expires_at is None
            or row.expires_at <= now
        ):
            raise OwnershipLost("Publication ownership expired or superseded")
        row.next_publish_at = now + timedelta(seconds=REPUBLISH_SECONDS)
        row.token = None
        row.expires_at = None


async def delivery_status(
    sessions: async_sessionmaker[AsyncSession], *, run_id: UUID, queue_url: str, profile: str
) -> str | None:
    """Untrusted UUIDs cannot adopt jobs outside this destination/profile."""
    async with sessions() as session:
        status = await session.scalar(
            select(RunRow.status)
            .join(JobRow, JobRow.run_id == RunRow.id)
            .join(OutboxRow, OutboxRow.run_id == RunRow.id)
            .where(RunRow.id == run_id, JobRow.profile == profile, OutboxRow.queue_url == queue_url)
        )
        assert status is None or isinstance(status, str)
        return status
