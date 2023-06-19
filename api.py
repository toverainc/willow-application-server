import json
from fastapi import FastAPI, Header, WebSocket, WebSocketDisconnect, WebSocketException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from logging import getLogger
from os import environ as env
from typing import Annotated
from websockets.exceptions import ConnectionClosed

app = FastAPI()
log = getLogger("WAS")
websocket = WebSocket


class Client:
    def __init__(self, ua):
        self.hostname = "unknown"
        self.ua = ua

    def set_hostname(self, hostname):
        self.hostname = hostname


class ConnMgr:
    def __init__(self):
        self.connected_clients: Dict[WebSocket, Client] = {}

    async def accept(self, ws: WebSocket, client: Client):
        try:
            await ws.accept()
            self.connected_clients[ws] = client
        except WebSocketException as e:
            log.error(f"failed to accept websocket connection: {e}")

    async def broadcast(self, ws: websocket, msg: str):
        for client in self.connected_clients:
            try:
                await client.send_text(msg)
            except WebSocketException as e:
                log.error(f"failed to broadcast message: {e}")

    def disconnect(self, ws: WebSocket):
        self.connected_clients.pop(ws)

    def update_client(self, ws, key, value):
        if key == "hostname":
            self.connected_clients[ws].set_hostname(value)


app.mount("/static", StaticFiles(directory="static"), name="static")
connmgr = ConnMgr()


def build_config_msg(config):
    try:
        msg = json.dumps({'config': json.loads(config)}, sort_keys=True)
        return msg
    except Exception as e:
        log.error(f"failed to build config message: {e}")

def get_config_ws():
    config = None
    try:
        with open("user_config.json", "r") as config_file:
            config = config_file.read()
    except Exception as e:
        log.error(f"failed to get config: {e}")
    finally:
        config_file.close()
        return config

@app.get("/")
def read_root():
    return {"Hello": "World"}

@app.get("/api/clients")
async def get_clients():
    clients = []
    for ws, client in connmgr.connected_clients.items():
        clients.append({'hostname': client.hostname, 'ip': ws.client.host, 'port': ws.client.port, 'user_agent': client.ua})

    return JSONResponse(content=clients)

@app.get("/api/config")
async def get_config():
    try:
        with open("user_config.json", "r") as config_file:
            user_config = json.load(config_file)
    except:
        user_config = {}

    return JSONResponse(content=user_config)

@app.post("/api/config")
async def post_config(request: Request):
    data = await request.json()
    with open("user_config.json", "w") as config_file:
        config_file.write(data)
    msg = build_config_msg(data)
    log.info(str(msg))
    await connmgr.broadcast(websocket, msg)
    return "Success"

@app.post("/api/ota")
async def post_ota():
    msg = json.dumps({'cmd':'ota_start', 'ota_url': env['OTA_URL']})
    for client in connmgr.connected_clients:
        try:
            await client.send_text(msg)
        except Exception as e:
            log.error("failed to trigger OTA")

@app.websocket("/ws")
async def websocket_endpoint(websocket: websocket, user_agent: Annotated[str | None, Header(convert_underscores=True)] = None):
    client = Client(user_agent)

    await connmgr.accept(websocket, client)
    try:
        while True:
            data = await websocket.receive_text()
            log.info(str(data))
            msg = json.loads(data)
            if "cmd" in msg:
                if msg["cmd"] == "get_config":
                    await websocket.send_text(build_config_msg(get_config_ws()))

            elif "hello" in msg:
                if "hostname" in msg["hello"]:
                    connmgr.update_client(websocket, "hostname", msg["hello"]["hostname"])

            else:
                await connmgr.broadcast(websocket, data)
    except WebSocketDisconnect:
        connmgr.disconnect(websocket)
    except ConnectionClosed:
        connmgr.disconnect(websocket)
