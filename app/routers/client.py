import json

from logging import getLogger
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..const import STORAGE_USER_CLIENT_CONFIG
from ..internal.was import device_command, get_devices, warm_tts


log = getLogger("WAS")
router = APIRouter(
    prefix="/api",
)


@router.get("/client")
async def api_get_client(request: Request):
    log.debug('API GET CLIENT: Request')
    devices = get_devices()
    clients = []
    macs = []
    labels = {}

    # This is ugly but it provides a combined response
    for ws, client in request.app.connmgr.connected_clients.items():
        if client.mac_addr not in macs:
            labels.update({client.mac_addr: None})
            for device in devices:
                if device["mac_addr"] == client.mac_addr:
                    if device["label"]:
                        labels.update({client.mac_addr: device["label"]})
            version = client.ua.replace("Willow/", "")
            clients.append({
                'hostname': client.hostname,
                'platform': client.platform,
                'mac_addr': client.mac_addr,
                'ip': ws.client.host,
                'port': ws.client.port,
                'version': version,
                'label': labels[client.mac_addr]
            })
            macs.append(client.mac_addr)

    # Sort connected clients by label if we have it
    # If all devices don't have labels we fall back to sorting by hostname
    try:
        sorted_clients = sorted(clients, key=lambda x: x['label'])
    except Exception:
        sorted_clients = sorted(clients, key=lambda x: x['hostname'])

    return JSONResponse(content=sorted_clients)


class PostClient(BaseModel):
    action: Literal['restart', 'update', 'config', 'identify', 'notify'] = Field(
        Query(..., description='Client action')
    )


@router.post("/client")
async def api_post_client(request: Request, device: PostClient = Depends()):
    log.debug('API POST CLIENT: Request')
    data = await request.json()

    if device.action == "update":
        msg = json.dumps({'cmd': 'ota_start', 'ota_url': data["ota_url"]})
        try:
            ws = request.app.connmgr.get_client_by_hostname(data["hostname"])
            await ws.send_text(msg)
        except Exception as e:
            log.error(f"Failed to trigger OTA ({e})")
        finally:
            return
    elif device.action == "config":
        devices = get_devices()
        new = True

        for i, device in enumerate(devices):
            if device.get("mac_addr") == data['mac_addr']:
                new = False
                devices[i] = data
                break

        if new and len(data['mac_addr']) > 0:
            devices.append(data)

        with open(STORAGE_USER_CLIENT_CONFIG, "w") as devices_file:
            json.dump(devices, devices_file)
        devices_file.close()
    elif device.action == 'notify':
        log.debug(f"received notify command on API: {data}")
        warm_tts(data["data"])
        request.app.notify_queue.add(data)
    else:
        # Catch all assuming anything else is a device command
        return await device_command(request.app.connmgr, data, device.action)
