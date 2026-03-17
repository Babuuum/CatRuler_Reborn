from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "56c998de8fc9"
down_revision: str | Sequence[str] | None = "95ab8c6de4f9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE post_status_enum ADD VALUE IF NOT EXISTS 'in_progress'")
        return

    with op.batch_alter_table("post_queue", recreate="always") as batch_op:
        batch_op.alter_column(
            "status",
            existing_type=sa.Enum(
                "pending",
                "sent",
                "failed",
                name="post_status_enum",
            ),
            type_=sa.Enum(
                "pending",
                "in_progress",
                "sent",
                "failed",
                name="post_status_enum",
            ),
            existing_nullable=False,
        )


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    status_rows = bind.execute(
        sa.text("SELECT COUNT(*) FROM post_queue WHERE status = 'in_progress'")
    ).scalar_one()
    if status_rows:
        raise RuntimeError(
            "Cannot downgrade while post_queue contains rows with status "
            "'in_progress'."
        )

    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE post_status_enum RENAME TO post_status_enum_old")
        op.execute("CREATE TYPE post_status_enum AS ENUM ('pending', 'sent', 'failed')")
        op.execute(
            """
            ALTER TABLE post_queue
            ALTER COLUMN status TYPE post_status_enum
            USING status::text::post_status_enum
            """
        )
        op.execute("DROP TYPE post_status_enum_old")
        return

    with op.batch_alter_table("post_queue", recreate="always") as batch_op:
        batch_op.alter_column(
            "status",
            existing_type=sa.Enum(
                "pending",
                "in_progress",
                "sent",
                "failed",
                name="post_status_enum",
            ),
            type_=sa.Enum(
                "pending",
                "sent",
                "failed",
                name="post_status_enum",
            ),
            existing_nullable=False,
        )
