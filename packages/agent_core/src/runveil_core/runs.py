"""Explicit run lifecycle, without execution or provider behavior."""

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from uuid import UUID

from runveil_core.errors import InvalidTransition


class RunStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"
    RETRYING = "RETRYING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


TERMINAL_STATUSES = frozenset({RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED})
TRANSITIONS = MappingProxyType(
    {
        RunStatus.QUEUED: frozenset({RunStatus.RUNNING, RunStatus.CANCELLED}),
        RunStatus.RUNNING: frozenset(
            {RunStatus.WAITING_FOR_APPROVAL, RunStatus.RETRYING, *TERMINAL_STATUSES}
        ),
        RunStatus.WAITING_FOR_APPROVAL: frozenset(
            {RunStatus.RUNNING, RunStatus.FAILED, RunStatus.CANCELLED}
        ),
        RunStatus.RETRYING: frozenset({RunStatus.RUNNING, RunStatus.FAILED, RunStatus.CANCELLED}),
        RunStatus.SUCCEEDED: frozenset(),
        RunStatus.FAILED: frozenset(),
        RunStatus.CANCELLED: frozenset(),
    }
)


@dataclass(frozen=True)
class Run:
    id: UUID
    agent_version_id: UUID
    status: RunStatus
    revision: int
    created_at: datetime
    state_changed_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None

    def transition(self, target: RunStatus, *, at: datetime) -> "Run":
        if target not in TRANSITIONS[self.status]:
            raise InvalidTransition(f"Cannot transition {self.status} to {target}")
        if at.utcoffset() is None or at < self.state_changed_at:
            raise ValueError("Transition time must be timezone-aware and not move backwards")
        return replace(
            self,
            status=target,
            revision=self.revision + 1,
            state_changed_at=at,
            started_at=self.started_at or (at if target == RunStatus.RUNNING else None),
            finished_at=at if target in TERMINAL_STATUSES else None,
        )
