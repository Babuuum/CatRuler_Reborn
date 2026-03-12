from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx
import redis.asyncio as aioredis

from app.core.settings import get_settings

DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=30.0, pool=5.0)
TOKEN_TTL_SECONDS = 60 * 60 * 24 * 6


@dataclass(slots=True)
class BotAPIError(Exception):
    message: str
    status_code: int | None = None

    def __str__(self) -> str:
        return self.message


_token_owner_cache: dict[str, int] = {}


def _get_redis() -> aioredis.Redis:
    return aioredis.from_url(get_settings().REDIS_URL, decode_responses=True)


def _token_cache_key(telegram_id: int) -> str:
    return f"bot:token:{telegram_id}"


def _forget_local_tokens(telegram_id: int) -> None:
    stale_tokens = [
        token
        for token, cached_telegram_id in _token_owner_cache.items()
        if cached_telegram_id == telegram_id
    ]
    for token in stale_tokens:
        _token_owner_cache.pop(token, None)


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
    token = str(data["access_token"])
    _token_owner_cache[token] = telegram_id
    return token


async def invalidate_token(telegram_id: int) -> None:
    _forget_local_tokens(telegram_id)
    redis = _get_redis()
    try:
        await redis.delete(_token_cache_key(telegram_id))
    finally:
        await redis.aclose()


async def _get_cached_token(telegram_id: int) -> str | None:
    redis = _get_redis()
    try:
        token = await redis.get(_token_cache_key(telegram_id))
    finally:
        await redis.aclose()

    if token:
        _token_owner_cache[token] = telegram_id
    return token


async def _cache_token(telegram_id: int, token: str) -> None:
    redis = _get_redis()
    try:
        await redis.set(_token_cache_key(telegram_id), token, ex=TOKEN_TTL_SECONDS)
    finally:
        await redis.aclose()


async def _refresh_token(telegram_id: int) -> str:
    password = await get_api_password(telegram_id)
    token = await login(telegram_id, password)
    await _cache_token(telegram_id, token)
    return token


async def _authorized_request(
    method: str,
    path: str,
    *,
    token: str,
    json: dict[str, Any] | None = None,
) -> Any:
    try:
        return await _request(
            method,
            path,
            headers={"Authorization": f"Bearer {token}"},
            json=json,
        )
    except BotAPIError as exc:
        if exc.status_code != 401:
            raise

    telegram_id = _token_owner_cache.pop(token, None)
    if telegram_id is None:
        raise BotAPIError("Token expired", status_code=401)

    await invalidate_token(telegram_id)
    refreshed_token = await _refresh_token(telegram_id)
    return await _request(
        method,
        path,
        headers={"Authorization": f"Bearer {refreshed_token}"},
        json=json,
    )


async def get_profile(token: str) -> dict[str, Any]:
    data = await _authorized_request(
        "GET",
        "/users/me",
        token=token,
    )
    return dict(data)


async def get_stats(token: str) -> dict[str, Any]:
    data = await _authorized_request(
        "GET",
        "/users/me/stats",
        token=token,
    )
    return dict(data)


async def get_channels(token: str) -> list[dict[str, Any]]:
    data = await _authorized_request(
        "GET",
        "/channels",
        token=token,
    )
    return [dict(item) for item in data]


async def generate_text_image(
    token: str,
    text_prompt: str,
    image_prompt: str,
) -> dict[str, Any]:
    data = await _authorized_request(
        "POST",
        "/generate/text-image",
        token=token,
        json={"text_prompt": text_prompt, "image_prompt": image_prompt},
    )
    return dict(data)


async def get_or_refresh_token(telegram_id: int) -> str:
    token = await _get_cached_token(telegram_id)
    if token:
        return token

    return await _refresh_token(telegram_id)


def clear_cached_token(telegram_id: int) -> None:
    loop = asyncio.get_running_loop()
    loop.create_task(invalidate_token(telegram_id))
