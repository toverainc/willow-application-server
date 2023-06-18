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
    def __init__(self, ua, ws):
        self.ua = ua
        self.ws = ws


class ConnMgr:
    def __init__(self):
        self.connected_clients: list[Client] = []

    async def accept(self, client: Client):
        try:
            await client.ws.accept()
            self.connected_clients.append(client)
        except WebSocketException as e:
            log.error(f"failed to accept websocket connection: {e}")

    async def broadcast(self, ws: websocket, msg: str):
        for client in self.connected_clients:
            try:
                await client.ws.send_text(msg)
            except WebSocketException as e:
                log.error(f"failed to broadcast message: {e}")

    def disconnect(self, client: Client):
        self.connected_clients.remove(client)


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
    for client in connmgr.connected_clients:
        clients.append(client.ua)

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
            await client.ws.send_text(msg)
        except Exception as e:
            log.error("failed to trigger OTA")

@app.websocket("/ws")
async def websocket_endpoint(websocket: websocket, user_agent: Annotated[str | None, Header(convert_underscores=True)] = None):
    client = Client(user_agent, websocket)

    await connmgr.accept(client)
    try:
        while True:
            data = await websocket.receive_text()
            log.info(str(data))
            msg = json.loads(data)
            if "cmd" in msg:
                if msg["cmd"] == "get_config":
                    await websocket.send_text(build_config_msg(get_config_ws()))

            else:
                await connmgr.broadcast(websocket, data)
    except WebSocketDisconnect:
        connmgr.disconnect(client)
    except ConnectionClosed:
        connmgr.disconnect(client)
