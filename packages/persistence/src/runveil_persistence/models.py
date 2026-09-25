"""Internal ORM mappings. Public repository results are domain snapshots."""

from datetime import datetime
from uuid import UUID

from runveil_core.agents import JsonValue
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
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
