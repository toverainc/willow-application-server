from logging import getLogger
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field
from requests import get

from ..const import URL_WILLOW_CONFIG
from ..internal.was import construct_url, get_config, get_multinet, get_nvs, get_tz_config, get_was_config


log = getLogger("WAS")
router = APIRouter(prefix="/api")


class GetConfig(BaseModel):
    type: Literal['config', 'nvs', 'ha_url', 'ha_token', 'multinet', 'was', 'tz'] = Field(
        Query(..., description='Configuration type')
    )
    default: Optional[bool] = False


@router.get("/config")
async def api_get_config(config: GetConfig = Depends()):
    log.debug('API GET CONFIG: Request')
    # TZ is special
    if config.type == "tz":
        config = get_tz_config(refresh=config.default)
        return JSONResponse(content=config)

    # Otherwise handle other config types
    if config.default:
        default_config = get(f"{URL_WILLOW_CONFIG}?type={config.type}").json()
        if type(default_config) == dict:
            return default_config
        else:
            raise HTTPException(status_code=400, detail="Invalid default config")

    if config.type == "nvs":
        nvs = get_nvs()
        return JSONResponse(content=nvs)
    elif config.type == "config":
        config = get_config()
        return JSONResponse(content=config)
    elif config.type == "ha_token":
        config = get_config()
        return PlainTextResponse(config["hass_token"])
    elif config.type == "ha_url":
        config = get_config()
        url = construct_url(config["hass_host"], config["hass_port"], config["hass_tls"])
        return PlainTextResponse(url)
    elif config.type == "multinet":
        config = get_multinet()
        return JSONResponse(content=config)
    elif config.type == "was":
        config = get_was_config()
        return JSONResponse(content=config)
