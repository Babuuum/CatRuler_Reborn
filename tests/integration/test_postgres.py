import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

from alembic.script import ScriptDirectory
from app.core.db.models.models import User
from tests.database import alembic_config, upgrade_test_database


async def test_commits_visible_to_other_sessions_and_rollback_isolated(session_maker):
    async with session_maker() as writer, session_maker() as reader:
        user = User(telegram_id=91001)
        writer.add(user)
        await writer.flush()
        assert await reader.get(User, user.id) is None
        await writer.commit()
        assert (await reader.get(User, user.id)).telegram_id == 91001

        writer.add(User(telegram_id=91002))
        await writer.flush()
        await writer.rollback()
        result = await reader.execute(select(User).where(User.telegram_id == 91002))
        assert result.scalar_one_or_none() is None


async def test_row_lock_blocks_an_independent_transaction(session_maker):
    async with session_maker() as setup:
        user = User(telegram_id=92001)
        setup.add(user)
        await setup.commit()
        user_id = user.id

    async with session_maker() as first, session_maker() as second:
        query = select(User).where(User.id == user_id).with_for_update()
        await first.execute(query)
        await second.execute(text("SET LOCAL lock_timeout = '100ms'"))
        with pytest.raises(DBAPIError) as error:
            await second.execute(query)
        assert error.value.orig.sqlstate == "55P03"
        await second.rollback()
        await first.rollback()
        # The competing transaction can acquire the row after release.
        await second.execute(text("SET LOCAL lock_timeout = '1s'"))
        assert (await second.execute(query)).scalar_one().id == user_id


async def test_migrations_reach_head_and_support_publish_status(db_engine):
    heads = ScriptDirectory.from_config(alembic_config()).get_heads()
    async with db_engine.connect() as connection:
        revisions = (
            (await connection.execute(text("SELECT version_num FROM alembic_version")))
            .scalars()
            .all()
        )
        assert sorted(revisions) == sorted(heads)
        status = await connection.scalar(
            text("SELECT 'in_progress'::post_status_enum::text")
        )
        assert status == "in_progress"


async def test_upgrade_preserves_existing_user_and_adds_model_defaults(
    postgres_database,
):
    await asyncio.to_thread(upgrade_test_database, postgres_database, "56c998de8fc9")
    engine = create_async_engine(postgres_database)
    user_id = uuid4()
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO users (id, telegram_id, plan, extended_free) "
                    "VALUES (:id, 93001, 'free', false)"
                ),
                {"id": user_id},
            )
        await asyncio.to_thread(upgrade_test_database, postgres_database)
        async with engine.connect() as connection:
            row = (
                await connection.execute(
                    text(
                        "SELECT id, text_model_key, image_model_key FROM users WHERE telegram_id = 93001"
                    )
                )
            ).one()
            assert row.id == user_id
            assert row.text_model_key == "or_gemini"
            assert row.image_model_key == "pollen_flux"
    finally:
        await engine.dispose()
