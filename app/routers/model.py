from logging import getLogger
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from requests import get

from app.const import URL_WILLOW_MODELS
from app.internal.was import get_models


log = getLogger("WAS")
router = APIRouter(
    prefix="/api",
)


class GetModel(BaseModel):
    type: Literal["wakenet"] = Field(
        Query(..., description="Model type")
    )


@router.get("/model")
async def api_get_model(asset: GetModel = Depends()):
    log.debug("API GET MODEL: Request")

    models = get_models()

    return JSONResponse(content=models)
