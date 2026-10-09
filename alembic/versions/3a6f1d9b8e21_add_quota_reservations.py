"""add generation quota reservations

Revision ID: 3a6f1d9b8e21
Revises: d9c7eb4abdd8
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "3a6f1d9b8e21"
down_revision: str | Sequence[str] | None = "d9c7eb4abdd8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    status_enum = sa.Enum(
        "reserved",
        "consumed",
        "released",
        name="quota_reservation_status_enum",
    )
    op.create_table(
        "quota_reservations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("operation_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("day_utc", sa.Date(), nullable=False),
        sa.Column("text_units", sa.Integer(), nullable=False),
        sa.Column("image_units", sa.Integer(), nullable=False),
        sa.Column("units", sa.Integer(), nullable=False),
        sa.Column("status", status_enum, nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("finalized_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("operation_id"),
        sa.CheckConstraint("units > 0", name="ck_quota_reservations_units_positive"),
        sa.CheckConstraint(
            "text_units >= 0 AND image_units >= 0",
            name="ck_quota_reservations_units_nonnegative",
        ),
        sa.CheckConstraint(
            "units = text_units + image_units",
            name="ck_quota_reservations_units_exact",
        ),
    )
    op.create_index(
        "ix_quota_reservations_user_day_status_expires",
        "quota_reservations",
        ["user_id", "day_utc", "status", "expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_quota_reservations_user_day_status_expires",
        table_name="quota_reservations",
    )
    op.drop_table("quota_reservations")
    sa.Enum(name="quota_reservation_status_enum").drop(op.get_bind(), checkfirst=True)
