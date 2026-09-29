"""Opt-in recurring broker notifications.

Revision ID: 0007
Revises: 0006
"""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "worker_outbox",
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("queue_url", sa.String(2048), nullable=False),
        sa.Column(
            "next_publish_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("token", sa.Uuid(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("run_id", name="pk_worker_outbox"),
        sa.ForeignKeyConstraint(["run_id"], ["worker_jobs.run_id"], ondelete="RESTRICT"),
        sa.CheckConstraint("length(queue_url) BETWEEN 1 AND 2048", name="queue_url_length"),
        sa.CheckConstraint("(token IS NULL) = (expires_at IS NULL)", name="publication_lease_pair"),
    )
    op.create_index("ix_worker_outbox_due", "worker_outbox", ["queue_url", "next_publish_at"])
    op.execute("""
        CREATE FUNCTION guard_worker_outbox() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'Outbox enrollment cannot be deleted' USING ERRCODE = '23514';
            END IF;
            IF (NEW.run_id, NEW.queue_url) IS DISTINCT FROM (OLD.run_id, OLD.queue_url) THEN
                RAISE EXCEPTION 'Outbox destination is immutable' USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END; $$;
        CREATE TRIGGER immutable_worker_outbox BEFORE UPDATE OR DELETE ON worker_outbox
            FOR EACH ROW EXECUTE FUNCTION guard_worker_outbox();
    """)


def downgrade() -> None:
    op.drop_table("worker_outbox")
    op.execute("DROP FUNCTION guard_worker_outbox()")
