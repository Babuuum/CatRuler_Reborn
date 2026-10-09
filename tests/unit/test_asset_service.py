from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.services import asset_service


@pytest.mark.asyncio
async def test_download_asset_requires_owner(mocker):
    mocker.patch.object(asset_service.asset_repo, "get_owned", return_value=None)

    with pytest.raises(HTTPException) as error:
        await asset_service.download_owned_image(object(), uuid4(), uuid4())

    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_download_asset_uses_server_resolved_key(mocker):
    asset = SimpleNamespace(object_key="generated/user/image.jpg")
    mocker.patch.object(asset_service.asset_repo, "get_owned", return_value=asset)
    download = mocker.patch.object(
        asset_service.storage,
        "download_file",
        new=mocker.AsyncMock(return_value=b"image"),
    )

    result = await asset_service.download_owned_image(object(), uuid4(), uuid4())

    assert result == b"image"
    download.assert_awaited_once_with(asset.object_key)
