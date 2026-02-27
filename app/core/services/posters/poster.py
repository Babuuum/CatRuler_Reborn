


# dobavit' v utils iniciali3aciu configov i deshifrator
# rasstavit' taimouti
# sam poster
# dobavit' infy o publike v db

# o4ered' na4at' delat'
# scheduler
# infrostryktyra, docker, ruff

# loggirovanie + neiroconfig
# endpointi + db crud

# perepisat' eto

import asyncio
import httpx
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path
from abc import ABC, abstractmethod


# ---------------------------------------------------------------------------
# Модели
# ---------------------------------------------------------------------------

@dataclass
class Platform:
    type: str          # "telegram" | "vk"
    channel_id: str    # @channel / -100xxx для TG, group_id для VK
    token: str         # токен бота / access token


@dataclass
class PublishResult:
    platform: str
    channel_id: str
    success: bool
    post_id: Optional[str] = None
    post_url: Optional[str] = None
    error: Optional[str] = None

    def __str__(self):
        if self.success:
            return f"[{self.platform}] ✅ {self.channel_id} → {self.post_url or self.post_id}"
        return f"[{self.platform}] ❌ {self.channel_id} — {self.error}"


# ---------------------------------------------------------------------------
# Базовый адаптер (добавить новую платформу = унаследовать этот класс)
# ---------------------------------------------------------------------------

class BaseAdapter(ABC):
    def __init__(self, platform: Platform):
        self.platform = platform

    @abstractmethod
    async def publish(
        self,
        text: str,
        image_path: Optional[str] = None,
    ) -> PublishResult:
        ...


# ---------------------------------------------------------------------------
# Telegram Bot API
# ---------------------------------------------------------------------------

class TelegramAdapter(BaseAdapter):
    BASE = "https://api.telegram.org/bot{token}/{method}"

    def _url(self, method: str) -> str:
        return self.BASE.format(token=self.platform.token, method=method)

    async def publish(self, text: str, image_path: Optional[str] = None) -> PublishResult:
        async with httpx.AsyncClient(timeout=60) as client:
            if image_path:
                return await self._send_photo(client, text, image_path)
            return await self._send_message(client, text)

    async def _send_message(self, client: httpx.AsyncClient, text: str) -> PublishResult:
        r = await client.post(self._url("sendMessage"), json={
            "chat_id": self.platform.channel_id,
            "text": text,
            "parse_mode": "HTML",
        })
        return self._parse(r.json())

    async def _send_photo(self, client: httpx.AsyncClient, caption: str, image_path: str) -> PublishResult:
        image = Path(image_path)
        with image.open("rb") as f:
            r = await client.post(
                self._url("sendPhoto"),
                data={"chat_id": self.platform.channel_id, "caption": caption, "parse_mode": "HTML"},
                files={"photo": (image.name, f, "image/jpeg")},
            )
        return self._parse(r.json())

    def _parse(self, data: dict) -> PublishResult:
        if data.get("ok"):
            msg = data["result"]
            return PublishResult(
                platform="telegram",
                channel_id=self.platform.channel_id,
                success=True,
                post_id=str(msg["message_id"]),
            )
        return PublishResult(
            platform="telegram",
            channel_id=self.platform.channel_id,
            success=False,
            error=data.get("description", "unknown error"),
        )


# ---------------------------------------------------------------------------
# VKontakte API
# ---------------------------------------------------------------------------

class VKAdapter(BaseAdapter):
    BASE = "https://api.vk.com/method/{method}"
    VERSION = "5.199"

    def _params(self, **kwargs) -> dict:
        return {"access_token": self.platform.token, "v": self.VERSION, **kwargs}

    async def publish(self, text: str, image_path: Optional[str] = None) -> PublishResult:
        async with httpx.AsyncClient(timeout=60) as client:
            attachment = None
            if image_path:
                attachment = await self._upload_photo(client, image_path)
                if attachment is None:
                    return PublishResult(
                        platform="vk",
                        channel_id=self.platform.channel_id,
                        success=False,
                        error="Ошибка загрузки фото",
                    )
            return await self._wall_post(client, text, attachment)

    async def _upload_photo(self, client: httpx.AsyncClient, image_path: str) -> Optional[str]:
        # 1. Получаем upload URL
        r = await client.get(self.BASE.format(method="photos.getWallUploadServer"),
                             params=self._params(group_id=self.platform.channel_id))
        data = r.json()
        if "error" in data:
            return None
        upload_url = data["response"]["upload_url"]

        # 2. Загружаем файл
        image = Path(image_path)
        with image.open("rb") as f:
            r = await client.post(upload_url, files={"photo": (image.name, f, "image/jpeg")})
        uploaded = r.json()

        # 3. Сохраняем
        r = await client.post(self.BASE.format(method="photos.saveWallPhoto"),
                              params=self._params(
                                  group_id=self.platform.channel_id,
                                  photo=uploaded["photo"],
                                  server=uploaded["server"],
                                  hash=uploaded["hash"],
                              ))
        saved = r.json()
        if "error" in saved:
            return None
        photo = saved["response"][0]
        return f"photo{photo['owner_id']}_{photo['id']}"

    async def _wall_post(self, client: httpx.AsyncClient, text: str, attachment: Optional[str]) -> PublishResult:
        params = self._params(
            owner_id=f"-{self.platform.channel_id}",
            from_group=1,
            message=text,
        )
        if attachment:
            params["attachments"] = attachment

        r = await client.post(self.BASE.format(method="wall.post"), params=params)
        data = r.json()

        if "error" in data:
            return PublishResult(
                platform="vk",
                channel_id=self.platform.channel_id,
                success=False,
                error=data["error"].get("error_msg", "unknown error"),
            )
        post_id = data["response"]["post_id"]
        return PublishResult(
            platform="vk",
            channel_id=self.platform.channel_id,
            success=True,
            post_id=str(post_id),
            post_url=f"https://vk.com/wall-{self.platform.channel_id}_{post_id}",
        )


# ---------------------------------------------------------------------------
# Реестр адаптеров — сюда добавлять новые платформы
# ---------------------------------------------------------------------------

ADAPTERS: dict[str, type[BaseAdapter]] = {
    "telegram": TelegramAdapter,
    "vk": VKAdapter,
    # "instagram": InstagramAdapter,  # пример расширения
}


# ---------------------------------------------------------------------------
# Главный класс
# ---------------------------------------------------------------------------

class SocialPublisher:
    """
    Публикует контент в список платформ параллельно.

    Args:
        platforms: список Platform с типом, channel_id и токеном.

    Example:
        publisher = SocialPublisher([
            Platform("telegram", "@news_channel", "TG_TOKEN"),
            Platform("vk", "987654321", "VK_TOKEN"),
        ])
        results = await publisher.publish("Текст поста", image_path="img.jpg")
    """

    def __init__(self, platforms: list[Platform]):
        self._adapters: list[BaseAdapter] = []
        for p in platforms:
            adapter_cls = ADAPTERS.get(p.type.lower())
            if adapter_cls is None:
                raise ValueError(f"Неизвестная платформа: '{p.type}'. Доступны: {list(ADAPTERS)}")
            self._adapters.append(adapter_cls(p))

    async def publish(
        self,
        text: str,
        image_path: Optional[str] = None,
    ) -> list[PublishResult]:
        """Публикует во все платформы параллельно, возвращает список результатов."""
        tasks = [a.publish(text, image_path) for a in self._adapters]
        return await asyncio.gather(*tasks)

    def publish_sync(
        self,
        text: str,
        image_path: Optional[str] = None,
    ) -> list[PublishResult]:
        """Синхронная обёртка для использования вне async-контекста."""
        return asyncio.run(self.publish(text, image_path))


# ---------------------------------------------------------------------------
# Пример использования
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import asyncio

    publisher = SocialPublisher([
        Platform(type="telegram", channel_id="@my_channel",  token="TG_BOT_TOKEN"),
        Platform(type="vk",       channel_id="123456789",    token="VK_ACCESS_TOKEN"),
    ])

    results = asyncio.run(publisher.publish(
        text="Тестовая публикация 🚀",
        # image_path="photo.jpg",  # раскомментировать для фото
    ))

    for r in results:
        print(r)