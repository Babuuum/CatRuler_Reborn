import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.core.db.base import Base
from app.core.generation_models import (
    DEFAULT_IMAGE_MODEL_KEY,
    DEFAULT_TEXT_MODEL_KEY,
)
from app.core.utils.crypto import decrypt, encrypt

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class PlanEnum(str, enum.Enum):
    free = "free"
    base = "base"
    pro = "pro"


class PlatformEnum(str, enum.Enum):
    vk = "vk"
    telegram = "telegram"


class PostStatusEnum(str, enum.Enum):
    pending = "pending"
    in_progress = "in_progress"
    sent = "sent"
    failed = "failed"


class ContentTypeEnum(str, enum.Enum):
    text = "text"
    image = "image"
    text_image = "text_image"


class ActionEnum(str, enum.Enum):
    post_generated = "post_generated"
    post_sent = "post_sent"
    image_generated = "image_generated"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    plan: Mapped[PlanEnum] = mapped_column(
        Enum(PlanEnum, name="plan_enum"), nullable=False, default=PlanEnum.free
    )
    extended_free: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    api_password_hash: Mapped[str | None] = mapped_column(
        String, nullable=True, default=None
    )
    text_model_key: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default=DEFAULT_TEXT_MODEL_KEY,
        server_default=DEFAULT_TEXT_MODEL_KEY,
    )
    image_model_key: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default=DEFAULT_IMAGE_MODEL_KEY,
        server_default=DEFAULT_IMAGE_MODEL_KEY,
    )
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now()
    )

    channels: Mapped[list["Channel"]] = relationship(back_populates="user")
    usage_logs: Mapped[list["UsageLog"]] = relationship(back_populates="user")


class Channel(Base):
    __tablename__ = "channels"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    platform: Mapped[PlatformEnum] = mapped_column(
        Enum(PlatformEnum, name="platform_enum"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now()
    )

    # Relations
    user: Mapped["User"] = relationship(back_populates="channels")
    post_queue: Mapped[list["PostQueue"]] = relationship(back_populates="channel")

    vk_config: Mapped[Optional["VKChannelConfig"]] = relationship(
        back_populates="channel",
        uselist=False,
        cascade="all, delete-orphan",
    )
    tg_config: Mapped[Optional["TGChannelConfig"]] = relationship(
        back_populates="channel",
        uselist=False,
        cascade="all, delete-orphan",
    )

    @property
    def config(self) -> "VKChannelConfig | TGChannelConfig | None":
        """Универсальный доступ к конфигу текущей платформы"""
        if self.platform == PlatformEnum.vk:
            return self.vk_config
        if self.platform == PlatformEnum.telegram:
            return self.tg_config
        return None


class VKChannelConfig(Base):
    __tablename__ = "vk_channel_configs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    channel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    group_id: Mapped[str] = mapped_column(String, nullable=False)

    _community_token: Mapped[str] = mapped_column(
        "community_token", String, nullable=False
    )

    @validates("_community_token")
    def encrypt_token(self, key: str, value: str) -> str:
        return encrypt(value)

    @property
    def community_token(self) -> str:
        return decrypt(self._community_token)

    channel: Mapped["Channel"] = relationship(back_populates="vk_config")


class TGChannelConfig(Base):
    __tablename__ = "tg_channel_configs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    channel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,  # One-to-One
    )
    chat_id: Mapped[str] = mapped_column(String, nullable=False)

    channel: Mapped["Channel"] = relationship(back_populates="tg_config")


class PostQueue(Base):
    __tablename__ = "post_queue"
    __table_args__ = (
        Index("ix_post_queue_status_scheduled_at", "status", "scheduled_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    channel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"), nullable=False
    )
    scheduled_at: Mapped[datetime] = mapped_column(nullable=False)
    status: Mapped[PostStatusEnum] = mapped_column(
        Enum(PostStatusEnum, name="post_status_enum"),
        nullable=False,
        default=PostStatusEnum.pending,
    )
    content_type: Mapped[ContentTypeEnum] = mapped_column(
        Enum(ContentTypeEnum, name="content_type_enum"), nullable=False
    )
    text_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_image_key: Mapped[str | None] = mapped_column(String, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now()
    )

    channel: Mapped["Channel"] = relationship(back_populates="post_queue")


class UsageLog(Base):
    __tablename__ = "usage_logs"
    __table_args__ = (
        Index(
            "ix_usage_logs_user_action_created_at", "user_id", "action", "created_at"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    action: Mapped[ActionEnum] = mapped_column(
        Enum(ActionEnum, name="action_enum"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="usage_logs")


class AdPost(Base):
    __tablename__ = "ad_posts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_url: Mapped[str | None] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
