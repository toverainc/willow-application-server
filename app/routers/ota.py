import os

from logging import getLogger
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from requests import get

from ..const import DIR_OTA
from ..internal.was import get_releases_willow, is_safe_path


log = getLogger("WAS")
router = APIRouter(prefix="/api")


class GetOta(BaseModel):
    version: str = Field(Query(..., description='OTA Version'))
    platform: str = Field(Query(..., description='OTA Platform'))


@router.get("/ota")
async def api_get_ota(ota: GetOta = Depends()):
    log.debug('API GET OTA: Request')
    ota_dir = is_safe_path(DIR_OTA, os.path.join(DIR_OTA, ota.version))
    ota_file = os.path.join(ota_dir, f"{ota.platform}.bin")
    ota_file = is_safe_path(ota_dir, ota_file)
    if not ota_file:
        return
    if not os.path.isfile(ota_file):
        releases = get_releases_willow()
        for release in releases:
            if release["name"] == ota.version:
                assets = release["assets"]
                for asset in assets:
                    if asset["platform"] == ota.platform:
                        Path(ota_dir).mkdir(parents=True, exist_ok=True)
                        r = get(asset["browser_download_url"])
                        open(ota_file, 'wb').write(r.content)

    # If we still don't have the file return 404 - the platform and/or version doesn't exist
    if not os.path.isfile(ota_file):
        raise HTTPException(status_code=404, detail="OTA File Not Found")

    return FileResponse(ota_file)
