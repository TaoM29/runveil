"""Durable single-proposal review.

Revision ID: 0009
Revises: 0008
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "approval_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "run_id", sa.Uuid(), sa.ForeignKey("runs.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("proposal", JSONB(), nullable=False),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="PENDING"),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.clock_timestamp(),
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("run_id", name="uq_approval_requests_run"),
        sa.CheckConstraint("jsonb_typeof(proposal) = 'object'", name="proposal_object"),
        sa.CheckConstraint("digest ~ '^[0-9a-f]{64}$'", name="proposal_digest"),
        sa.CheckConstraint(
            "(status = 'PENDING' AND decided_at IS NULL) OR "
            "(status IN ('APPROVED', 'REJECTED') AND decided_at IS NOT NULL "
            "AND decided_at >= requested_at)",
            name="approval_outcome",
        ),
    )
    op.execute("""
        CREATE FUNCTION guard_approval_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'Approval request is immutable' USING ERRCODE = '23514';
            END IF;
            IF OLD.status != 'PENDING' OR NEW.status NOT IN ('APPROVED', 'REJECTED')
               OR NEW.decided_at IS NULL
               OR (NEW.id, NEW.run_id, NEW.proposal, NEW.digest, NEW.requested_at)
                   IS DISTINCT FROM
                  (OLD.id, OLD.run_id, OLD.proposal, OLD.digest, OLD.requested_at) THEN
                RAISE EXCEPTION 'Approval identity/outcome is immutable' USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END; $$;
        CREATE TRIGGER immutable_approval BEFORE UPDATE OR DELETE ON approval_requests
            FOR EACH ROW EXECUTE FUNCTION guard_approval_mutation();
    """)


def downgrade() -> None:
    op.drop_table("approval_requests")
    op.execute("DROP FUNCTION guard_approval_mutation()")
