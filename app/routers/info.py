from logging import getLogger
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.settings import Settings, get_settings


log = getLogger("WAS")

router = APIRouter(
    prefix="/api",
)


@router.get("/info")
async def api_get_info(settings: Annotated[Settings, Depends(get_settings)]):
    log.debug('API GET VERSION: Request')

    info = {
        'was': {
            'version': settings.was_version,
        }
    }

    return JSONResponse(info)
