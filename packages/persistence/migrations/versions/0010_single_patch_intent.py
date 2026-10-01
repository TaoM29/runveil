"""Single-use patch intent.

Revision ID: 0010
Revises: 0009
"""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "uq_tool_calls_single_patch",
        "tool_calls",
        ["run_id"],
        unique=True,
        postgresql_where=sa.text("tool_name = 'repository.apply_patch'"),
    )


def downgrade() -> None:
    op.drop_index("uq_tool_calls_single_patch", table_name="tool_calls")
