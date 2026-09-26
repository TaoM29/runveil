"""Internal ORM mappings. Public repository results are domain snapshots."""

from datetime import datetime
from uuid import UUID

from runveil_core.agents import JsonValue
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    MetaData,
    String,
    UniqueConstraint,
    func,
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
