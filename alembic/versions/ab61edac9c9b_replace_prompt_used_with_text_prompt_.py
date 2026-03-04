"""replace prompt_used with text_prompt and image_prompt in post_queue

Revision ID: ab61edac9c9b
Revises: 3424ea030c5d
Create Date: 2026-03-04 11:24:38.780357

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ab61edac9c9b"
down_revision: str | Sequence[str] | None = "3424ea030c5d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("post_queue", sa.Column("text_prompt", sa.Text(), nullable=True))
    op.add_column("post_queue", sa.Column("image_prompt", sa.Text(), nullable=True))
    op.drop_column("post_queue", "prompt_used")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column("post_queue", sa.Column("prompt_used", sa.Text(), nullable=True))
    op.drop_column("post_queue", "image_prompt")
    op.drop_column("post_queue", "text_prompt")
