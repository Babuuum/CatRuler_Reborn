"""add performance indexes

Revision ID: d9c7eb4abdd8
Revises: c6f8e5b7a9d1
Create Date: 2026-03-19 00:27:34.787688

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d9c7eb4abdd8"
down_revision: str | Sequence[str] | None = "c6f8e5b7a9d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index("ix_channels_user_id", "channels", ["user_id"], unique=False)
    op.create_index(
        "ix_post_queue_status_scheduled_at",
        "post_queue",
        ["status", "scheduled_at"],
        unique=False,
    )
    op.create_index(
        "ix_usage_logs_user_action_created_at",
        "usage_logs",
        ["user_id", "action", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "ix_usage_logs_user_action_created_at",
        table_name="usage_logs",
    )
    op.drop_index(
        "ix_post_queue_status_scheduled_at",
        table_name="post_queue",
    )
    op.drop_index("ix_channels_user_id", table_name="channels")
