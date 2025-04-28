import os

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from logging import getLogger
from typing import Literal
from pydantic import BaseModel, Field

from ..const import DIR_ASSET
from ..internal.was import get_mime_type, get_safe_path


log = getLogger("WAS")
router = APIRouter(
    prefix="/api",
)


class GetAsset(BaseModel):
    asset: str = Field(Query(..., description="Asset"))
    type: Literal["audio", "image", "other"] = Field(
        Query(..., description="Asset type")
    )


@router.get("/asset")
async def api_get_asset(asset: GetAsset = Depends()):
    log.debug("API GET ASSET: Request")
    asset_file = os.path.join(DIR_ASSET, asset.type, asset.asset)
    asset_file = get_safe_path(DIR_ASSET, asset_file)
    log.debug(f"asset file: {asset_file}")

    # If we don't have the asset file return 404
    if not os.path.isfile(asset_file):
        raise HTTPException(status_code=404, detail="Asset File Not Found")

    # Use libmagic to determine MIME type to be really sure
    magic_mime_type = get_mime_type(asset_file)

    # Return image and other types
    if asset.type == "image" or asset.type == "other":
        return FileResponse(asset_file, media_type=magic_mime_type)

    # Only support audio formats supported by Willow
    if magic_mime_type == "audio/flac" or magic_mime_type == "audio/x-wav":
        return FileResponse(asset_file, media_type=magic_mime_type)
    else:
        raise HTTPException(status_code=400, detail="unsupported Audio Asset file format")
