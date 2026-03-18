"""add model keys to users

Revision ID: c6f8e5b7a9d1
Revises: 56c998de8fc9
Create Date: 2026-03-17 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c6f8e5b7a9d1"
down_revision: str | Sequence[str] | None = "56c998de8fc9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "users",
        sa.Column(
            "text_model_key",
            sa.String(),
            nullable=False,
            server_default="or_gemini",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "image_model_key",
            sa.String(),
            nullable=False,
            server_default="pollen_flux",
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("users", "image_model_key")
    op.drop_column("users", "text_model_key")
