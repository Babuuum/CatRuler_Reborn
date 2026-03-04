import secrets
import string
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.models.models import User
from app.core.logger import get_logger
from app.repositories import user_repo
from app.schemas.user import UserResponse, UserUpdate

logger = get_logger(__name__)


def _to_user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        telegram_id=user.telegram_id,
        plan=user.plan,
        extended_free=user.extended_free,
        has_api_password=bool(getattr(user, "api_password_hash", None)),
        created_at=user.created_at,
    )


def _generate_password(length: int = 16) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


async def get_me(db: AsyncSession, user_id: UUID) -> UserResponse:
    user = await user_repo.get_by_id(db, user_id)
    if user is None:
        raise ValueError("User not found")
    return _to_user_response(user)


async def update_me(db: AsyncSession, user_id: UUID, data: UserUpdate) -> UserResponse:
    payload = data.model_dump(exclude_unset=True)
    user = await user_repo.update(db, user_id, payload)
    return _to_user_response(user)


async def get_or_create(db: AsyncSession, telegram_id: int) -> User:
    user, _ = await user_repo.get_or_create(db, telegram_id)
    return user


async def generate_api_password(db: AsyncSession, user_id: UUID) -> str:
    try:
        import bcrypt
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("bcrypt dependency is required") from exc

    password = _generate_password()
    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode(
        "utf-8"
    )
    await user_repo.update(db, user_id, {"api_password_hash": password_hash})
    logger.info("api_password_generated", user_id=str(user_id))
    return password
