"""Durable worker enrollment and leases.

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "worker_jobs",
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("task", sa.String(16384), nullable=False),
        sa.Column("profile", sa.String(100), nullable=False),
        sa.Column("token", sa.Uuid(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("run_id", name="pk_worker_jobs"),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("length(task) BETWEEN 1 AND 16384", name="task_length"),
        sa.CheckConstraint("length(profile) BETWEEN 1 AND 100", name="profile_length"),
        sa.CheckConstraint("(token IS NULL) = (expires_at IS NULL)", name="lease_pair"),
    )
    op.execute("""
        CREATE FUNCTION guard_worker_job() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'Worker enrollment cannot be deleted' USING ERRCODE = '23514';
            END IF;
            IF TG_OP = 'UPDATE' AND
               (NEW.run_id, NEW.task, NEW.profile) IS DISTINCT FROM
               (OLD.run_id, OLD.task, OLD.profile) THEN
                RAISE EXCEPTION 'Worker enrollment is immutable' USING ERRCODE = '23514';
            END IF;
            IF TG_OP = 'INSERT' THEN
                PERFORM 1 FROM runs WHERE id=NEW.run_id AND status='QUEUED' FOR UPDATE;
                IF NOT FOUND THEN
                    RAISE EXCEPTION 'Enrollment requires queued run' USING ERRCODE = '23514';
                END IF;
            END IF;
            RETURN NEW;
        END; $$;
        CREATE TRIGGER valid_worker_job BEFORE INSERT OR UPDATE OR DELETE ON worker_jobs
            FOR EACH ROW EXECUTE FUNCTION guard_worker_job();
    """)


def downgrade() -> None:
    op.drop_table("worker_jobs")
    op.execute("DROP FUNCTION guard_worker_job()")
