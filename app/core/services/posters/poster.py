import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx
import structlog

from app.core.settings import get_settings

logger = structlog.get_logger(__name__)


@dataclass
class Platform:
    type: str
    channel_id: str
    token: str


@dataclass
class PublishResult:
    platform: str
    channel_id: str
    success: bool
    post_id: str | None = None
    post_url: str | None = None
    error: str | None = None


class BaseAdapter(ABC):
    def __init__(self, platform: Platform):
        self.platform = platform

    @abstractmethod
    async def publish(
        self,
        text: str,
        image_bytes: bytes | None = None,
    ) -> PublishResult: ...

    def _timeout(self) -> httpx.Timeout:
        timeout = get_settings().PUBLISH_REQUEST_TIMEOUT
        return httpx.Timeout(timeout=timeout, connect=min(timeout, 5.0))


class TelegramAdapter(BaseAdapter):
    BASE = "https://api.telegram.org/bot{token}/{method}"

    def _url(self, method: str) -> str:
        return self.BASE.format(token=self.platform.token, method=method)

    async def publish(
        self,
        text: str,
        image_bytes: bytes | None = None,
    ) -> PublishResult:
        try:
            async with httpx.AsyncClient(timeout=self._timeout()) as client:
                if image_bytes:
                    return await self._send_photo(client, text, image_bytes)
                return await self._send_message(client, text)
        except httpx.HTTPError as exc:
            return PublishResult(
                platform="telegram",
                channel_id=self.platform.channel_id,
                success=False,
                error=str(exc),
            )

    async def _send_message(
        self,
        client: httpx.AsyncClient,
        text: str,
    ) -> PublishResult:
        response = await client.post(
            self._url("sendMessage"),
            json={
                "chat_id": self.platform.channel_id,
                "text": text,
                "parse_mode": "HTML",
            },
        )
        response.raise_for_status()
        return self._parse(response.json())

    async def _send_photo(
        self,
        client: httpx.AsyncClient,
        caption: str,
        image_bytes: bytes,
    ) -> PublishResult:
        response = await client.post(
            self._url("sendPhoto"),
            data={
                "chat_id": self.platform.channel_id,
                "caption": caption,
                "parse_mode": "HTML",
            },
            files={"photo": ("image.jpg", image_bytes, "image/jpeg")},
        )
        response.raise_for_status()
        return self._parse(response.json())

    def _parse(self, data: dict) -> PublishResult:
        if data.get("ok"):
            message = data["result"]
            post_id = str(message["message_id"])
            return PublishResult(
                platform="telegram",
                channel_id=self.platform.channel_id,
                success=True,
                post_id=post_id,
                post_url=self._build_post_url(post_id),
            )
        return PublishResult(
            platform="telegram",
            channel_id=self.platform.channel_id,
            success=False,
            error=data.get("description", "unknown error"),
        )

    def _build_post_url(self, post_id: str) -> str | None:
        if self.platform.channel_id.startswith("@"):
            return f"https://t.me/{self.platform.channel_id[1:]}/{post_id}"
        return None


class VKAdapter(BaseAdapter):
    BASE = "https://api.vk.com/method/{method}"
    VERSION = "5.199"

    def _params(self, **kwargs: str | int) -> dict[str, str | int]:
        return {"access_token": self.platform.token, "v": self.VERSION, **kwargs}

    async def publish(
        self,
        text: str,
        image_bytes: bytes | None = None,
    ) -> PublishResult:
        try:
            async with httpx.AsyncClient(timeout=self._timeout()) as client:
                attachment = None
                if image_bytes:
                    attachment = await self._upload_photo(client, image_bytes)
                    if attachment is None:
                        return PublishResult(
                            platform="vk",
                            channel_id=self.platform.channel_id,
                            success=False,
                            error="Failed to upload photo",
                        )
                return await self._wall_post(client, text, attachment)
        except httpx.HTTPError as exc:
            return PublishResult(
                platform="vk",
                channel_id=self.platform.channel_id,
                success=False,
                error=str(exc),
            )

    async def _upload_photo(
        self,
        client: httpx.AsyncClient,
        image_bytes: bytes,
    ) -> str | None:
        response = await client.get(
            self.BASE.format(method="photos.getWallUploadServer"),
            params=self._params(group_id=self.platform.channel_id),
        )
        response.raise_for_status()
        upload_server = response.json()
        if "error" in upload_server:
            return None

        upload_url = upload_server["response"]["upload_url"]
        uploaded_response = await client.post(
            upload_url,
            files={"photo": ("image.jpg", image_bytes, "image/jpeg")},
        )
        uploaded_response.raise_for_status()
        uploaded = uploaded_response.json()

        save_response = await client.post(
            self.BASE.format(method="photos.saveWallPhoto"),
            params=self._params(
                group_id=self.platform.channel_id,
                photo=uploaded["photo"],
                server=uploaded["server"],
                hash=uploaded["hash"],
            ),
        )
        save_response.raise_for_status()
        saved = save_response.json()
        if "error" in saved:
            return None

        photo = saved["response"][0]
        return f"photo{photo['owner_id']}_{photo['id']}"

    async def _wall_post(
        self,
        client: httpx.AsyncClient,
        text: str,
        attachment: str | None,
    ) -> PublishResult:
        params = self._params(
            owner_id=f"-{self.platform.channel_id}",
            from_group=1,
            message=text,
        )
        if attachment:
            params["attachments"] = attachment

        response = await client.post(
            self.BASE.format(method="wall.post"),
            params=params,
        )
        response.raise_for_status()
        data = response.json()

        if "error" in data:
            return PublishResult(
                platform="vk",
                channel_id=self.platform.channel_id,
                success=False,
                error=data["error"].get("error_msg", "unknown error"),
            )

        post_id = str(data["response"]["post_id"])
        return PublishResult(
            platform="vk",
            channel_id=self.platform.channel_id,
            success=True,
            post_id=post_id,
            post_url=f"https://vk.com/wall-{self.platform.channel_id}_{post_id}",
        )


ADAPTERS: dict[str, type[BaseAdapter]] = {
    "telegram": TelegramAdapter,
    "vk": VKAdapter,
}


class SocialPublisher:
    def __init__(self, platforms: list[Platform]):
        self._adapters: list[BaseAdapter] = []
        for platform in platforms:
            adapter_cls = ADAPTERS.get(platform.type.lower())
            if adapter_cls is None:
                raise ValueError(
                    f"Unknown platform '{platform.type}'. Available: {list(ADAPTERS)}"
                )
            self._adapters.append(adapter_cls(platform))

    async def publish(
        self,
        text: str,
        image_bytes: bytes | None = None,
    ) -> list[PublishResult]:
        results = await asyncio.gather(
            *(adapter.publish(text, image_bytes) for adapter in self._adapters)
        )
        for result in results:
            logger.info(
                "publish_result",
                platform=result.platform,
                channel_id=result.channel_id,
                success=result.success,
                post_id=result.post_id,
                post_url=result.post_url,
                error=result.error,
            )
        return results

    def publish_sync(
        self,
        text: str,
        image_bytes: bytes | None = None,
    ) -> list[PublishResult]:
        return asyncio.run(self.publish(text, image_bytes))
