"""Immutable execution deadline for budgeted worker jobs.

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "worker_jobs", sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.execute("""
        CREATE FUNCTION guard_worker_deadline() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF OLD.deadline_at IS NOT NULL AND NEW.deadline_at IS DISTINCT FROM OLD.deadline_at THEN
                RAISE EXCEPTION 'Assigned deadline is immutable' USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END; $$;
        CREATE TRIGGER immutable_worker_deadline BEFORE UPDATE ON worker_jobs
            FOR EACH ROW EXECUTE FUNCTION guard_worker_deadline();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER immutable_worker_deadline ON worker_jobs")
    op.execute("DROP FUNCTION guard_worker_deadline()")
    op.drop_column("worker_jobs", "deadline_at")
