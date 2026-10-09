"""add owned generated assets and publication attempt state."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "5e2a7b1c4d90"
down_revision: str | Sequence[str] | None = "3a6f1d9b8e21"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE post_status_enum ADD VALUE IF NOT EXISTS 'unknown'")

    op.create_table(
        "generated_assets",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("object_key", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("object_key"),
    )
    op.create_index("ix_generated_assets_user_id", "generated_assets", ["user_id"])

    op.add_column(
        "post_queue",
        sa.Column("generated_asset_id", sa.UUID(), nullable=True),
    )
    op.add_column(
        "post_queue", sa.Column("idempotency_key", sa.String(), nullable=True)
    )
    op.create_foreign_key(
        "fk_post_queue_generated_asset_id",
        "post_queue",
        "generated_assets",
        ["generated_asset_id"],
        ["id"],
        ondelete="SET NULL",
    )
    for name, column in (
        ("publish_attempt_id", sa.UUID()),
        ("publish_owner", sa.String()),
        ("publish_started_at", sa.DateTime()),
        ("publish_lease_expires_at", sa.DateTime()),
        ("external_post_id", sa.String()),
        ("external_post_url", sa.String()),
    ):
        op.add_column("post_queue", sa.Column(name, column, nullable=True))
    op.create_index(
        "ix_post_queue_publish_lease",
        "post_queue",
        ["status", "publish_lease_expires_at"],
    )
    op.create_unique_constraint(
        "uq_post_queue_channel_idempotency_key",
        "post_queue",
        ["channel_id", "idempotency_key"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    unknown_rows = bind.execute(
        sa.text("SELECT COUNT(*) FROM post_queue WHERE status = 'unknown'")
    ).scalar_one()
    if unknown_rows:
        raise RuntimeError("Cannot downgrade while unknown publication attempts exist")

    op.drop_index("ix_post_queue_publish_lease", table_name="post_queue")
    op.drop_constraint(
        "uq_post_queue_channel_idempotency_key", "post_queue", type_="unique"
    )
    for name in (
        "external_post_url",
        "external_post_id",
        "publish_lease_expires_at",
        "publish_started_at",
        "publish_owner",
        "publish_attempt_id",
    ):
        op.drop_column("post_queue", name)
    op.drop_constraint(
        "fk_post_queue_generated_asset_id", "post_queue", type_="foreignkey"
    )
    op.drop_column("post_queue", "generated_asset_id")
    op.drop_column("post_queue", "idempotency_key")
    op.drop_index("ix_generated_assets_user_id", table_name="generated_assets")
    op.drop_table("generated_assets")

    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE post_status_enum RENAME TO post_status_enum_old")
        op.execute(
            "CREATE TYPE post_status_enum AS ENUM "
            "('pending', 'in_progress', 'sent', 'failed')"
        )
        op.execute(
            "ALTER TABLE post_queue ALTER COLUMN status TYPE post_status_enum "
            "USING status::text::post_status_enum"
        )
        op.execute("DROP TYPE post_status_enum_old")
