from logging import getLogger
from re import sub
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field
from requests import get

from app.db.main import get_config_db, get_nvs_db

from ..const import URL_WILLOW_CONFIG
from ..internal.command_endpoints.main import init_command_endpoint
from ..internal.was import (
    construct_url,
    get_multinet,
    get_tz_config,
    get_was_config,
    post_config,
    post_nvs,
    post_was,
)


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
        if isinstance(default_config, dict):
            return default_config
        else:
            raise HTTPException(status_code=400, detail="Invalid default config")

    if config.type == "nvs":
        nvs = get_nvs_db()
        return JSONResponse(content=nvs)
    elif config.type == "config":
        config = get_config_db()
        if "wis_tts_url_v2" in config:
            config["wis_tts_url"] = sub("[&?]text=", "", config["wis_tts_url_v2"])
            del config["wis_tts_url_v2"]
        return JSONResponse(content=config)
    elif config.type == "ha_token":
        config = get_config_db()
        return PlainTextResponse(config["hass_token"])
    elif config.type == "ha_url":
        config = get_config_db()
        url = construct_url(config["hass_host"], config["hass_port"], config["hass_tls"])
        return PlainTextResponse(url)
    elif config.type == "multinet":
        config = get_multinet()
        return JSONResponse(content=config)
    elif config.type == "was":
        config = get_was_config()
        return JSONResponse(content=config)


class PostConfig(BaseModel):
    type: Literal['config', 'nvs', 'was'] = Field(Query(..., description='Configuration type'))
    apply: bool = Field(Query(..., description='Apply configuration to device'))


@router.post("/config")
async def api_post_config(request: Request, config: PostConfig = Depends()):
    log.debug('API POST CONFIG: Request')
    if config.type == "config":
        await post_config(request, config.apply)
        init_command_endpoint(request.app)
    elif config.type == "nvs":
        await post_nvs(request, config.apply)
    elif config.type == "was":
        await post_was(request, config.apply)
