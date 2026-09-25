"""Agent definitions, immutable versions and guarded run lifecycle.

Revision ID: 0001
Revises: None
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_definitions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "length(trim(name)) > 0", name=op.f("ck_agent_definitions_name_not_blank")
        ),
        sa.PrimaryKeyConstraint("id", name="pk_agent_definitions"),
    )
    op.create_table(
        "agent_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("agent_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("configuration", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("number > 0", name=op.f("ck_agent_versions_positive_number")),
        sa.CheckConstraint(
            "jsonb_typeof(configuration) = 'object'",
            name=op.f("ck_agent_versions_configuration_object"),
        ),
        sa.ForeignKeyConstraint(
            ["agent_id"],
            ["agent_definitions.id"],
            ondelete="RESTRICT",
            name="fk_agent_versions_agent_id_agent_definitions",
        ),
        sa.UniqueConstraint("agent_id", "number", name="uq_agent_versions_agent_number"),
        sa.PrimaryKeyConstraint("id", name="pk_agent_versions"),
    )
    op.create_table(
        "runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("agent_version_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(32), server_default="QUEUED", nullable=False),
        sa.Column("revision", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "state_changed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('QUEUED','RUNNING','WAITING_FOR_APPROVAL','RETRYING',"
            "'SUCCEEDED','FAILED','CANCELLED')",
            name=op.f("ck_runs_valid_status"),
        ),
        sa.CheckConstraint("revision >= 0", name=op.f("ck_runs_nonnegative_revision")),
        sa.CheckConstraint("state_changed_at >= created_at", name=op.f("ck_runs_ordered_change")),
        sa.CheckConstraint(
            "started_at IS NULL OR (started_at >= created_at AND started_at <= state_changed_at)",
            name=op.f("ck_runs_ordered_start"),
        ),
        sa.CheckConstraint(
            "(status IN ('SUCCEEDED','FAILED','CANCELLED')) = (finished_at IS NOT NULL)",
            name=op.f("ck_runs_terminal_time"),
        ),
        sa.CheckConstraint(
            "finished_at IS NULL OR finished_at = state_changed_at",
            name=op.f("ck_runs_ordered_finish"),
        ),
        sa.CheckConstraint(
            "status IN ('QUEUED','CANCELLED') OR started_at IS NOT NULL",
            name=op.f("ck_runs_started_state"),
        ),
        sa.CheckConstraint(
            "status != 'QUEUED' OR started_at IS NULL", name=op.f("ck_runs_queued_not_started")
        ),
        sa.ForeignKeyConstraint(
            ["agent_version_id"],
            ["agent_versions.id"],
            ondelete="RESTRICT",
            name="fk_runs_agent_version_id_agent_versions",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_runs"),
    )
    op.create_index("ix_runs_agent_version_id", "runs", ["agent_version_id"])
    op.execute("""
        CREATE FUNCTION reject_agent_version_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'Agent versions are immutable; create a new version'
                USING ERRCODE = '23514';
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER immutable_agent_version BEFORE UPDATE OR DELETE ON agent_versions
        FOR EACH ROW EXECUTE FUNCTION reject_agent_version_mutation()
    """)
    op.execute("""
        CREATE FUNCTION guard_run_lifecycle() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                IF NEW.status != 'QUEUED' OR NEW.revision != 0
                   OR NEW.started_at IS NOT NULL OR NEW.finished_at IS NOT NULL
                   OR NEW.state_changed_at IS DISTINCT FROM NEW.created_at THEN
                    RAISE EXCEPTION 'Runs must begin queued at revision zero'
                        USING ERRCODE = '23514';
                END IF;
                RETURN NEW;
            END IF;
            IF NEW.id IS DISTINCT FROM OLD.id
               OR NEW.agent_version_id IS DISTINCT FROM OLD.agent_version_id
               OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
                RAISE EXCEPTION 'Run identity is immutable' USING ERRCODE = '23514';
            END IF;
            IF NOT (
                (OLD.status = 'QUEUED' AND NEW.status IN ('RUNNING','CANCELLED')) OR
                (OLD.status = 'RUNNING' AND NEW.status IN
                    ('WAITING_FOR_APPROVAL','RETRYING','SUCCEEDED','FAILED','CANCELLED')) OR
                (OLD.status IN ('WAITING_FOR_APPROVAL','RETRYING')
                    AND NEW.status IN ('RUNNING','FAILED','CANCELLED'))
            ) THEN
                RAISE EXCEPTION 'Invalid run transition' USING ERRCODE = '23514';
            END IF;
            IF NEW.revision != OLD.revision + 1 OR NEW.state_changed_at < OLD.state_changed_at THEN
                RAISE EXCEPTION 'Invalid run revision or transition time' USING ERRCODE = '23514';
            END IF;
            IF OLD.started_at IS NOT NULL THEN
                IF NEW.started_at IS DISTINCT FROM OLD.started_at THEN
                    RAISE EXCEPTION 'First start time is immutable' USING ERRCODE = '23514';
                END IF;
            ELSIF NEW.status = 'RUNNING' THEN
                IF NEW.started_at IS DISTINCT FROM NEW.state_changed_at THEN
                    RAISE EXCEPTION 'Start time must match first running transition'
                        USING ERRCODE = '23514';
                END IF;
            ELSIF NEW.started_at IS NOT NULL THEN
                RAISE EXCEPTION 'Run has not started' USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER valid_run_lifecycle BEFORE INSERT OR UPDATE ON runs
        FOR EACH ROW EXECUTE FUNCTION guard_run_lifecycle()
    """)


def downgrade() -> None:
    op.drop_table("runs")
    op.execute("DROP FUNCTION guard_run_lifecycle()")
    op.drop_table("agent_versions")
    op.execute("DROP FUNCTION reject_agent_version_mutation()")
    op.drop_table("agent_definitions")
