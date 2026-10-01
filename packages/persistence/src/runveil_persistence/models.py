"""Internal ORM mappings. Public repository results are domain snapshots."""

from datetime import datetime
from uuid import UUID

from runveil_core.agents import JsonValue
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    MetaData,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(table_name)s_%(column_0_name)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


class AgentRow(Base):
    __tablename__ = "agent_definitions"
    __table_args__ = (CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),)
    id: Mapped[UUID] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class VersionRow(Base):
    __tablename__ = "agent_versions"
    __table_args__ = (
        UniqueConstraint("agent_id", "number", name="uq_agent_versions_agent_number"),
        CheckConstraint("number > 0", name="positive_number"),
        CheckConstraint("jsonb_typeof(configuration) = 'object'", name="configuration_object"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    agent_id: Mapped[UUID] = mapped_column(ForeignKey("agent_definitions.id", ondelete="RESTRICT"))
    number: Mapped[int] = mapped_column(Integer)
    configuration: Mapped[dict[str, JsonValue]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RunRow(Base):
    __tablename__ = "runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('QUEUED','RUNNING','WAITING_FOR_APPROVAL','RETRYING',"
            "'SUCCEEDED','FAILED','CANCELLED')",
            name="valid_status",
        ),
        CheckConstraint("revision >= 0", name="nonnegative_revision"),
        CheckConstraint("state_changed_at >= created_at", name="ordered_change"),
        CheckConstraint(
            "started_at IS NULL OR (started_at >= created_at AND started_at <= state_changed_at)",
            name="ordered_start",
        ),
        CheckConstraint(
            "(status IN ('SUCCEEDED','FAILED','CANCELLED')) = (finished_at IS NOT NULL)",
            name="terminal_time",
        ),
        CheckConstraint(
            "finished_at IS NULL OR finished_at = state_changed_at", name="ordered_finish"
        ),
        CheckConstraint(
            "status IN ('QUEUED','CANCELLED') OR started_at IS NOT NULL", name="started_state"
        ),
        CheckConstraint("status != 'QUEUED' OR started_at IS NULL", name="queued_not_started"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    agent_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent_versions.id", ondelete="RESTRICT"), index=True
    )
    status: Mapped[str] = mapped_column(String(32), server_default="QUEUED")
    revision: Mapped[int] = mapped_column(Integer, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    state_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class StepRow(Base):
    __tablename__ = "run_steps"
    __table_args__ = (
        CheckConstraint("number > 0", name="positive_number"),
        CheckConstraint("kind ~ '^[a-z][a-z0-9_.]{0,99}$'", name="valid_kind"),
        CheckConstraint("jsonb_typeof(details) = 'object'", name="details_object"),
    )
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("runs.id", ondelete="RESTRICT"), primary_key=True
    )
    number: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(100))
    details: Mapped[dict[str, JsonValue]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )


class EventRow(Base):
    __tablename__ = "execution_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["run_id", "step_number"], ["run_steps.run_id", "run_steps.number"], ondelete="RESTRICT"
        ),
        CheckConstraint("sequence > 0", name="positive_sequence"),
        CheckConstraint("run_revision >= 0", name="nonnegative_revision"),
        CheckConstraint("jsonb_typeof(payload) = 'object'", name="payload_object"),
    )
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("runs.id", ondelete="RESTRICT"), primary_key=True
    )
    sequence: Mapped[int] = mapped_column(Integer, primary_key=True, server_default="0")
    kind: Mapped[str] = mapped_column(String(100))
    run_revision: Mapped[int] = mapped_column(Integer)
    step_number: Mapped[int | None] = mapped_column(Integer)
    payload: Mapped[dict[str, JsonValue]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )


class CheckpointRow(Base):
    __tablename__ = "checkpoints"
    __table_args__ = (
        ForeignKeyConstraint(
            ["run_id", "event_sequence"],
            ["execution_events.run_id", "execution_events.sequence"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["run_id", "step_number"], ["run_steps.run_id", "run_steps.number"], ondelete="RESTRICT"
        ),
        UniqueConstraint("run_id", "step_number", name="uq_checkpoints_run_step"),
        CheckConstraint("schema_version > 0", name="positive_schema_version"),
        CheckConstraint("run_revision >= 0", name="nonnegative_revision"),
        CheckConstraint("run_status = 'RUNNING'", name="running_boundary"),
        CheckConstraint("jsonb_typeof(state) = 'object'", name="state_object"),
    )
    run_id: Mapped[UUID] = mapped_column(primary_key=True)
    event_sequence: Mapped[int] = mapped_column(Integer, primary_key=True)
    step_number: Mapped[int] = mapped_column(Integer)
    run_revision: Mapped[int] = mapped_column(Integer)
    run_status: Mapped[str] = mapped_column(String(32))
    schema_version: Mapped[int] = mapped_column(Integer)
    state: Mapped[dict[str, JsonValue]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )


class InvocationColumns:
    """Shared columns for the two concrete request/outcome tables."""

    id: Mapped[UUID] = mapped_column(primary_key=True)
    run_id: Mapped[UUID] = mapped_column(ForeignKey("runs.id", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(String(16), server_default="REQUESTED")
    requested_event_sequence: Mapped[int] = mapped_column(Integer)
    completed_event_sequence: Mapped[int | None] = mapped_column(Integer)
    step_number: Mapped[int | None] = mapped_column(Integer)
    request: Mapped[dict[str, JsonValue]] = mapped_column(JSONB)
    result: Mapped[dict[str, JsonValue] | None] = mapped_column(JSONB(none_as_null=True))
    error_code: Mapped[str | None] = mapped_column(String(64))
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


def invocation_constraints(
    table: str,
) -> tuple[ForeignKeyConstraint | UniqueConstraint | CheckConstraint, ...]:
    return (
        UniqueConstraint("run_id", "id", name=f"uq_{table}_run_id"),
        UniqueConstraint("run_id", "requested_event_sequence", name=f"uq_{table}_request_event"),
        UniqueConstraint("run_id", "completed_event_sequence", name=f"uq_{table}_completion_event"),
        UniqueConstraint("run_id", "step_number", name=f"uq_{table}_step"),
        ForeignKeyConstraint(
            ["run_id", "requested_event_sequence"],
            ["execution_events.run_id", "execution_events.sequence"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["run_id", "completed_event_sequence"],
            ["execution_events.run_id", "execution_events.sequence"],
            ondelete="RESTRICT",
            name=f"fk_{table}_completion_event",
        ),
        ForeignKeyConstraint(
            ["run_id", "step_number"],
            ["checkpoints.run_id", "checkpoints.step_number"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("jsonb_typeof(request) = 'object'", name="request_object"),
        CheckConstraint("result IS NULL OR jsonb_typeof(result) = 'object'", name="result_object"),
        CheckConstraint(
            "error_code IS NULL OR error_code ~ '^[a-z][a-z0-9_]{0,63}$'", name="error_code"
        ),
        CheckConstraint(
            "(status = 'REQUESTED' AND result IS NULL AND error_code IS NULL "
            "AND completed_at IS NULL AND completed_event_sequence IS NULL "
            "AND step_number IS NULL) "
            "OR (status IN ('SUCCEEDED', 'FAILED') AND completed_at IS NOT NULL "
            "AND completed_event_sequence IS NOT NULL AND step_number IS NOT NULL "
            "AND ((status = 'SUCCEEDED' AND result IS NOT NULL AND error_code IS NULL) "
            "OR (status = 'FAILED' AND result IS NULL AND error_code IS NOT NULL)))",
            name="outcome",
        ),
        CheckConstraint(
            "completed_at IS NULL OR completed_at >= requested_at", name="ordered_time"
        ),
        CheckConstraint(
            "completed_event_sequence IS NULL OR "
            "completed_event_sequence > requested_event_sequence",
            name="ordered_events",
        ),
    )


class ModelInvocationRow(InvocationColumns, Base):
    __tablename__ = "model_invocations"
    __table_args__ = (
        *invocation_constraints("model_invocations"),
        CheckConstraint(
            "length(trim(provider)) > 0 AND provider !~ '[[:cntrl:]]'", name="provider"
        ),
        CheckConstraint("length(trim(model)) > 0 AND model !~ '[[:cntrl:]]'", name="model"),
    )
    provider: Mapped[str] = mapped_column(String(200))
    model: Mapped[str] = mapped_column(String(200))


class ToolCallRow(InvocationColumns, Base):
    __tablename__ = "tool_calls"
    __table_args__ = (
        *invocation_constraints("tool_calls"),
        Index(
            "uq_tool_calls_single_patch",
            "run_id",
            unique=True,
            postgresql_where=text("tool_name = 'repository.apply_patch'"),
        ),
        ForeignKeyConstraint(
            ["run_id", "model_invocation_id"],
            ["model_invocations.run_id", "model_invocations.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "length(trim(tool_name)) > 0 AND tool_name !~ '[[:cntrl:]]'", name="tool_name"
        ),
    )
    tool_name: Mapped[str] = mapped_column(String(200))
    model_invocation_id: Mapped[UUID | None] = mapped_column()


class JobRow(Base):
    __tablename__ = "worker_jobs"
    __table_args__ = (
        CheckConstraint("admission_failures BETWEEN 0 AND 3", name="admission_failures_bound"),
        CheckConstraint("admission_revision >= 0", name="admission_revision_nonnegative"),
        CheckConstraint(
            "(admission_failures = 3) = (quarantined_at IS NOT NULL)",
            name="admission_quarantine_pair",
        ),
        CheckConstraint("length(task) BETWEEN 1 AND 16384", name="task_length"),
        CheckConstraint("length(profile) BETWEEN 1 AND 100", name="profile_length"),
        CheckConstraint("(token IS NULL) = (expires_at IS NULL)", name="lease_pair"),
    )
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("runs.id", ondelete="RESTRICT"), primary_key=True
    )
    task: Mapped[str] = mapped_column(String(16384))
    profile: Mapped[str] = mapped_column(String(100))
    token: Mapped[UUID | None] = mapped_column()
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    admission_failures: Mapped[int] = mapped_column(Integer, server_default="0")
    admission_revision: Mapped[int] = mapped_column(Integer, server_default="0")
    admission_not_before: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    quarantined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OutboxRow(Base):
    __tablename__ = "worker_outbox"
    __table_args__ = (
        CheckConstraint("length(queue_url) BETWEEN 1 AND 2048", name="queue_url_length"),
        CheckConstraint("(token IS NULL) = (expires_at IS NULL)", name="publication_lease_pair"),
        Index("ix_worker_outbox_due", "queue_url", "next_publish_at"),
    )
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("worker_jobs.run_id", ondelete="RESTRICT"), primary_key=True
    )
    queue_url: Mapped[str] = mapped_column(String(2048))
    next_publish_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    token: Mapped[UUID | None] = mapped_column()
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AdmissionEventRow(Base):
    __tablename__ = "worker_admission_events"
    __table_args__ = (
        CheckConstraint("revision > 0", name="admission_event_revision"),
        CheckConstraint(
            "(action = 'rejected' AND failures BETWEEN 1 AND 3) "
            "OR (action = 'released' AND failures = 0)",
            name="admission_event_action",
        ),
    )
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("worker_jobs.run_id", ondelete="RESTRICT"), primary_key=True
    )
    revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    action: Mapped[str] = mapped_column(String(20))
    failures: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )


class ApprovalRow(Base):
    __tablename__ = "approval_requests"
    __table_args__ = (
        UniqueConstraint("run_id", name="uq_approval_requests_run"),
        CheckConstraint("jsonb_typeof(proposal) = 'object'", name="proposal_object"),
        CheckConstraint("digest ~ '^[0-9a-f]{64}$'", name="proposal_digest"),
        CheckConstraint(
            "(status = 'PENDING' AND decided_at IS NULL) OR "
            "(status IN ('APPROVED', 'REJECTED') AND decided_at IS NOT NULL "
            "AND decided_at >= requested_at)",
            name="approval_outcome",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    run_id: Mapped[UUID] = mapped_column(ForeignKey("runs.id", ondelete="RESTRICT"))
    proposal: Mapped[dict[str, JsonValue]] = mapped_column(JSONB)
    digest: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), server_default="PENDING")
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
