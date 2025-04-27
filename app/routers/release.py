import os

from logging import getLogger
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from requests import get

from ..const import DIR_OTA
from ..internal.was import get_release_url, get_releases_willow, get_was_url, is_safe_path


log = getLogger("WAS")
router = APIRouter(prefix="/api")


class GetRelease(BaseModel):
    type: Literal['was', 'willow'] = Field(Query(..., description='Release type'))


@router.get("/release")
async def api_get_release(release: GetRelease = Depends()):
    log.debug('API GET RELEASE: Request')
    releases = get_releases_willow()
    if release.type == "willow":
        return releases
    elif release.type == "was":
        was_url = get_was_url()
        if not was_url:
            raise HTTPException(status_code=500, detail="WAS URL not set")

        try:
            for release in releases:
                tag_name = release["tag_name"]
                assets = release["assets"]
                for asset in assets:
                    platform = asset["platform"]
                    asset["was_url"] = get_release_url(was_url, tag_name, platform)
                    if os.path.isfile(f"{DIR_OTA}/{tag_name}/{platform}.bin"):
                        asset["cached"] = True
                    else:
                        asset["cached"] = False
        except Exception as e:
            log.error(e)
            pass

        return JSONResponse(content=releases)


class PostRelease(BaseModel):
    action: Literal['delete'] = Field(Query(..., description='Release Cache Control'))


@router.post("/release")
async def api_post_release(request: Request, release: PostRelease = Depends()):
    log.debug('API POST RELEASE: Request')

    if release.action == "delete":
        data = await request.json()
        path = data['path']
        path = is_safe_path(DIR_OTA, path)
        if path:
            os.remove(path)
