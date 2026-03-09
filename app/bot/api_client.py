from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from app.core.settings import get_settings

DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=30.0, pool=5.0)


@dataclass(slots=True)
class BotAPIError(Exception):
    message: str
    status_code: int | None = None

    def __str__(self) -> str:
        return self.message


_token_cache: dict[int, str] = {}


async def _request(
    method: str,
    path: str,
    *,
    headers: dict[str, str] | None = None,
    json: dict[str, Any] | None = None,
) -> Any:
    settings = get_settings()

    async with httpx.AsyncClient(
        base_url=settings.INTERNAL_API_URL.rstrip("/"),
        timeout=DEFAULT_TIMEOUT,
    ) as client:
        try:
            response = await client.request(
                method=method,
                url=path,
                headers=headers,
                json=json,
            )
        except httpx.HTTPError as exc:
            raise BotAPIError("Internal API is unavailable") from exc

    if response.is_success:
        if not response.content:
            return None
        return response.json()

    try:
        payload = response.json()
    except ValueError:
        payload = {}

    detail = payload.get("detail")
    if isinstance(detail, list):
        detail = "; ".join(str(item) for item in detail)
    if not detail:
        detail = response.text or "Internal API request failed"

    raise BotAPIError(str(detail), status_code=response.status_code)


async def get_api_password(telegram_id: int) -> str:
    data = await _request(
        "POST",
        "/users/me/api-password",
        headers={"X-Telegram-Id": str(telegram_id)},
    )
    return str(data["password"])


async def login(telegram_id: int, password: str) -> str:
    data = await _request(
        "POST",
        "/auth/login",
        json={"telegram_id": telegram_id, "password": password},
    )
    return str(data["access_token"])


async def get_profile(token: str) -> dict[str, Any]:
    data = await _request(
        "GET",
        "/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    return dict(data)


async def get_stats(token: str) -> dict[str, Any]:
    data = await _request(
        "GET",
        "/users/me/stats",
        headers={"Authorization": f"Bearer {token}"},
    )
    return dict(data)


async def get_channels(token: str) -> list[dict[str, Any]]:
    data = await _request(
        "GET",
        "/channels",
        headers={"Authorization": f"Bearer {token}"},
    )
    return [dict(item) for item in data]


async def generate_text_image(
    token: str,
    text_prompt: str,
    image_prompt: str,
) -> dict[str, Any]:
    data = await _request(
        "POST",
        "/generate/text-image",
        headers={"Authorization": f"Bearer {token}"},
        json={"text_prompt": text_prompt, "image_prompt": image_prompt},
    )
    return dict(data)


async def get_or_refresh_token(telegram_id: int) -> str:
    token = _token_cache.get(telegram_id)
    if token:
        return token

    password = await get_api_password(telegram_id)
    token = await login(telegram_id, password)
    _token_cache[telegram_id] = token
    return token


def clear_cached_token(telegram_id: int) -> None:
    _token_cache.pop(telegram_id, None)
