from dataclasses import dataclass, field
from typing import Callable
import asyncio
import json
import httpx


# --- Конфиг ---

@dataclass
class APIConfig:
    url: str
    api_key: str
    model: str
    provider: str
    extra: dict = field(default_factory=dict)


@dataclass
class ProxyConfig:
    http: str | None = None
    https: str | None = None

    def to_httpx(self) -> dict[str, str]:
        proxies = {}
        if self.http:
            proxies["http://"] = self.http
        if self.https:
            proxies["https://"] = self.https
        return proxies


# --- Реестры моделей вместо Enum ---

class TextModels:
    OR_GEMINI = "or_gemini"
    OR_MISTRAL = "or_mistral"
    HF_DEEPSEEK = "hf_deepseek"
    HF_LLAMA = "hf_llama"
    HF_QWEN = "hf_qwen"
    HF_PHI = "hf_phi"


class ImageModels:
    POLLEN_FLUX = "pollen_flux"
    POLLEN_FLUX_REALISM = "pollen_flux_realism"
    POLLEN_TURBO = "pollen_turbo"
    HF_SD_SPACES = "hf_sd_spaces"


def build_text_registry(settings) -> dict[str, APIConfig]:
    return {
        TextModels.OR_GEMINI: APIConfig(
            url="https://openrouter.ai/api/v1/chat/completions",
            api_key=settings.OPEN_ROUTER_API_KEY,
            model="google/gemma-3-27b-it:free",
            provider="open_router",
        ),
        TextModels.OR_MISTRAL: APIConfig(
            url="https://openrouter.ai/api/v1/chat/completions",
            api_key=settings.OPEN_ROUTER_API_KEY,
            model="mistralai/mistral-7b-instruct:free",
            provider="open_router",
        ),
        TextModels.HF_DEEPSEEK: APIConfig(
            url="https://router.huggingface.co/v1/chat/completions",
            api_key=settings.HUGGING_FACE_API_KEY,
            model="deepseek-ai/DeepSeek-R1-0528",
            provider="hugging_face",
        ),
        TextModels.HF_LLAMA: APIConfig(
            url="https://router.huggingface.co/v1/chat/completions",
            api_key=settings.HUGGING_FACE_API_KEY,
            model="meta-llama/Llama-3.1-8B-Instruct",
            provider="hugging_face",
        ),
        TextModels.HF_QWEN: APIConfig(
            url="https://router.huggingface.co/v1/chat/completions",
            api_key=settings.HUGGING_FACE_API_KEY,
            model="Qwen/Qwen2.5-72B-Instruct",
            provider="hugging_face",
        ),
        TextModels.HF_PHI: APIConfig(
            url="https://router.huggingface.co/v1/chat/completions",
            api_key=settings.HUGGING_FACE_API_KEY,
            model="microsoft/Phi-3.5-mini-instruct",
            provider="hugging_face",
        ),
    }


def build_image_registry(settings) -> dict[str, APIConfig]:
    return {
        ImageModels.POLLEN_FLUX: APIConfig(
            url="https://gen.pollinations.ai/image/",
            api_key=settings.POLLEN_API_KEY,
            model="flux",
            provider="pollen",
        ),
        ImageModels.POLLEN_FLUX_REALISM: APIConfig(
            url="https://gen.pollinations.ai/image/",
            api_key=settings.POLLEN_API_KEY,
            model="flux-realism",
            provider="pollen",
        ),
        ImageModels.POLLEN_TURBO: APIConfig(
            url="https://gen.pollinations.ai/image/",
            api_key=settings.POLLEN_API_KEY,
            model="turbo",
            provider="pollen",
        ),
        ImageModels.HF_SD_SPACES: APIConfig(
            url="https://needchat-img-model.hf.space/gradio_api/call/infer",
            api_key=settings.HUGGING_FACE_API_KEY,
            model="stable-diffusion",
            provider="hugging_face_spaces",
            extra={"width": 1024, "height": 1024, "steps": 2},
        ),
    }


# --- Кастомные исключения ---

class ProviderError(Exception):
    def __init__(self, provider: str, reason: str):
        super().__init__(f"[{provider}] {reason}")
        self.provider = provider


# --- Результат ---

@dataclass
class GeneratedPost:
    text: str
    image_bytes: bytes          # единый тип — всегда байты
    text_model_used: str
    image_model_used: str
    prompt: str


# --- Генератор ---

class PostGenerator:
    def __init__(
        self,
        settings,                                    # передаём явно, не с модуля
        text_model: str = TextModels.OR_GEMINI,
        image_model: str = ImageModels.POLLEN_FLUX,
        proxy: ProxyConfig | None = None,
        timeout: int = 30,
    ):
        self._text_model = text_model
        self._image_model = image_model
        self._proxy = proxy
        self._timeout = timeout

        self._text_registry = build_text_registry(settings)
        self._image_registry = build_image_registry(settings)

        self._text_router: dict[str, Callable] = {
            "open_router":  self._generate_openai_compat,
            "hugging_face": self._generate_openai_compat,
        }
        self._image_router: dict[str, Callable] = {
            "pollen":              self._generate_pollen_image,
            "hugging_face_spaces": self._generate_hf_spaces_image,
        }

    def _make_client(self) -> httpx.AsyncClient:
        kwargs: dict = {"timeout": self._timeout}
        if self._proxy:
            kwargs["proxies"] = self._proxy.to_httpx()
        return httpx.AsyncClient(**kwargs)

    async def generate(self, prompt: str) -> GeneratedPost:
        if not prompt or not prompt.strip():
            raise ValueError("Prompt не может быть пустым")

        text_config = self._text_registry[self._text_model]
        image_config = self._image_registry[self._image_model]

        text_handler = self._text_router[text_config.provider]
        image_handler = self._image_router[image_config.provider]

        # один клиент на весь generate
        async with self._make_client() as client:
            text, image_bytes = await asyncio.gather(
                text_handler(prompt, text_config, client),
                image_handler(prompt, image_config, client),
            )

        return GeneratedPost(
            text=text,
            image_bytes=image_bytes,
            text_model_used=text_config.model,
            image_model_used=image_config.model,
            prompt=prompt,
        )

    async def _generate_openai_compat(
        self, prompt: str, config: APIConfig, client: httpx.AsyncClient
    ) -> str:
        try:
            response = await client.post(
                config.url,
                headers={"Authorization": f"Bearer {config.api_key}"},
                json={
                    "model": config.model,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]
        except httpx.HTTPStatusError as e:
            raise ProviderError(config.provider, f"HTTP {e.response.status_code}: {e.response.text}")
        except httpx.RequestError as e:
            raise ProviderError(config.provider, f"Ошибка соединения: {e}")

    async def _generate_pollen_image(
        self, prompt: str, config: APIConfig, client: httpx.AsyncClient
    ) -> bytes:
        from urllib.parse import quote
        try:
            url = f"{config.url}{quote(prompt)}"
            headers = {"Authorization": f"Bearer {config.api_key}"}
            params = {"model": config.model}
            if config.api_key:
                params["token"] = config.api_key

            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            return response.content
        except httpx.HTTPStatusError as e:
            raise ProviderError(config.provider, f"HTTP {e.response.status_code}: {e.response.text}")
        except httpx.RequestError as e:
            raise ProviderError(config.provider, f"Ошибка соединения: {e}")

    async def _generate_hf_spaces_image(
        self, prompt: str, config: APIConfig, client: httpx.AsyncClient
    ) -> bytes:
        extra = config.extra
        try:
            response = await client.post(
                config.url,
                headers={
                    "Authorization": f"Bearer {config.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "data": [
                        prompt, "",
                        0, True,
                        extra.get("width", 1024),
                        extra.get("height", 1024),
                        0.0,
                        extra.get("steps", 2),
                    ]
                },
            )
            response.raise_for_status()
            event_id = response.json()["event_id"]

            base = "https://needchat-img-model.hf.space"
            async with client.stream(
                "GET",
                f"{base}/gradio_api/call/infer/{event_id}",
                headers={"Authorization": f"Bearer {config.api_key}"},
            ) as sse:
                current_event = None
                async for line in sse.aiter_lines():
                    if not line:
                        continue
                    if line.startswith("event:"):
                        current_event = line.split(":", 1)[1].strip()
                    elif line.startswith("data:"):
                        data = json.loads(line.split(":", 1)[1].strip())
                        if current_event == "error":
                            raise ProviderError(config.provider, f"Spaces error: {data}")
                        if current_event == "complete":
                            image_url = data[0]["url"]
                            img_response = await client.get(image_url)
                            img_response.raise_for_status()
                            return img_response.content

        except ProviderError:
            raise
        except httpx.HTTPStatusError as e:
            raise ProviderError(config.provider, f"HTTP {e.response.status_code}: {e.response.text}")
        except httpx.RequestError as e:
            raise ProviderError(config.provider, f"Ошибка соединения: {e}")

        raise ProviderError(config.provider, "No complete event received")