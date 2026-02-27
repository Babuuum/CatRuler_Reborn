import aioboto3
import uuid
from app.core.settings import get_settings

settings = get_settings()

ENDPOINT = "https://storage.yandexcloud.net"
REGION = "ru-central1"


def _get_session():
    return aioboto3.Session(
    aws_access_key_id=settings.YANDEX_ACCESS_KEY,
    aws_secret_access_key=settings.YANDEX_SECRET_KEY,
    region_name=REGION
)


def _generate_key(ext: str = "jpg") -> str:
    """Генерирует уникальный key для объекта"""
    return f"images/{uuid.uuid4()}.{ext}"


async def upload_file(file: bytes, ext: str = "jpg") -> str:
    """Загружает файл в бакет, возвращает key"""
    key = _generate_key(ext)
    async with _get_session().client("s3", endpoint_url=ENDPOINT) as s3:
        await s3.put_object(
            Bucket=settings.BUCKET_NAME,
            Key=key,
            Body=file,
        )
    return key


async def download_file(key: str) -> bytes:
    """Скачивает файл из бакета по key"""
    async with _get_session().client("s3", endpoint_url=ENDPOINT) as s3:
        response = await s3.get_object(
            Bucket=settings.BUCKET_NAME,
            Key=key,
        )
        return await response["Body"].read()


async def delete_file(key: str) -> None:
    """Удаляет файл из бакета по key"""
    async with _get_session().client("s3", endpoint_url=ENDPOINT) as s3:
        await s3.delete_object(
            Bucket=settings.BUCKET_NAME,
            Key=key,
        )


async def update_file(old_key: str, new_file: bytes, ext: str = "jpg") -> str:
    """Удаляет старый файл, загружает новый, возвращает новый key"""
    await delete_file(old_key)
    return await upload_file(new_file, ext)