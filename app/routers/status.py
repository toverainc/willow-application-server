import asyncio

from logging import getLogger
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


log = getLogger("WAS")

router = APIRouter(
    prefix="/api",
)


class GetStatus(BaseModel):
    type: Literal['asyncio_tasks', 'connmgr', 'notify_queue'] = Field(Query(..., description='Status type'))


@router.get("/status")
async def api_get_status(request: Request, status: GetStatus = Depends()):
    log.debug('API GET STATUS: Request')
    res = []

    if status.type == "asyncio_tasks":
        tasks = asyncio.all_tasks()
        for task in tasks:
            res.append(f"{task.get_name()}: {task.get_coro()}")

    elif status.type == "connmgr":
        return JSONResponse(request.app.connmgr.model_dump(exclude={}))

    elif status.type == "notify_queue":
        return JSONResponse(request.app.notify_queue.model_dump(exclude={'connmgr', 'task'}))

    return JSONResponse(res)
