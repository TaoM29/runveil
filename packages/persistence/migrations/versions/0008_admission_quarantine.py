"""Durable admission cooldown, quarantine and separate immutable audit.

Revision ID: 0008
Revises: 0007
"""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "worker_jobs",
        sa.Column("admission_failures", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "worker_jobs",
        sa.Column("admission_revision", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "worker_jobs",
        sa.Column(
            "admission_not_before",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.add_column(
        "worker_jobs", sa.Column("quarantined_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_check_constraint(
        "admission_failures_bound", "worker_jobs", "admission_failures BETWEEN 0 AND 3"
    )
    op.create_check_constraint(
        "admission_revision_nonnegative", "worker_jobs", "admission_revision >= 0"
    )
    op.create_check_constraint(
        "admission_quarantine_pair",
        "worker_jobs",
        "(admission_failures = 3) = (quarantined_at IS NOT NULL)",
    )
    op.create_table(
        "worker_admission_events",
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("failures", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.clock_timestamp(),
        ),
        sa.PrimaryKeyConstraint("run_id", "revision", name="pk_worker_admission_events"),
        sa.ForeignKeyConstraint(["run_id"], ["worker_jobs.run_id"], ondelete="RESTRICT"),
        sa.CheckConstraint("revision > 0", name="admission_event_revision"),
        sa.CheckConstraint(
            "(action = 'rejected' AND failures BETWEEN 1 AND 3) "
            "OR (action = 'released' AND failures = 0)",
            name="admission_event_action",
        ),
    )
    op.execute("""
        CREATE FUNCTION reject_admission_event_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'Admission audit is append-only' USING ERRCODE = '23514';
        END; $$;
        CREATE TRIGGER immutable_admission_event BEFORE UPDATE OR DELETE ON worker_admission_events
            FOR EACH ROW EXECUTE FUNCTION reject_admission_event_mutation();
    """)


def downgrade() -> None:
    op.drop_table("worker_admission_events")
    op.execute("DROP FUNCTION reject_admission_event_mutation()")
    for name in (
        "admission_quarantine_pair",
        "admission_revision_nonnegative",
        "admission_failures_bound",
    ):
        op.drop_constraint(op.f("ck_worker_jobs_" + name), "worker_jobs", type_="check")
    for name in (
        "quarantined_at",
        "admission_not_before",
        "admission_revision",
        "admission_failures",
    ):
        op.drop_column("worker_jobs", name)
