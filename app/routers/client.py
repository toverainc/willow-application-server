from logging import getLogger

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse


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
        if not client.mac_addr in macs:
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
    except:
        sorted_clients = sorted(clients, key=lambda x: x['hostname'])

    return JSONResponse(content=sorted_clients)
