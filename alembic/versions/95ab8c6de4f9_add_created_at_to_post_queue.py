"""add created_at to post_queue

Revision ID: 95ab8c6de4f9
Revises: ab61edac9c9b
Create Date: 2026-03-04 11:38:43.759934

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "95ab8c6de4f9"
down_revision: str | Sequence[str] | None = "ab61edac9c9b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "post_queue",
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("post_queue", "created_at")
