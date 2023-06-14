import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, WebSocketException, Request
from fastapi.responses import JSONResponse
from logging import getLogger
from websockets.exceptions import ConnectionClosed

app = FastAPI()
log = getLogger("WAS")
websocket = WebSocket


class ConnMgr:
    def __init__(self):
        self.connected_clients: list[websocket] = []

    async def accept(self, ws: websocket):
        try:
            await ws.accept()
            self.connected_clients.append(ws)
        except WebSocketException as e:
            log.error(f"failed to accept websocket connection: {e}")

    async def broadcast(self, ws: websocket, msg: str):
        for client in self.connected_clients:
            try:
                await client.send_text(msg)
            except WebSocketException as e:
                log.error(f"failed to broadcast message: {e}")

    def disconnect(self, ws: websocket):
        self.connected_clients.remove(ws)


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

@app.get("/config")
async def get_config():
    try:
        with open("user_config.json", "r") as config_file:
            user_config = json.load(config_file)
    except:
        user_config = {}

    return JSONResponse(content=user_config)

@app.post("/config")
async def post_config(request: Request):
    data = await request.json()
    with open("user_config.json", "w") as config_file:
        config_file.write(data)
    msg = build_config_msg(data)
    log.info(str(msg))
    await connmgr.broadcast(websocket, msg)
    return "Success"

@app.websocket_route("/ws")
async def websocket_endpoint(websocket: websocket):
    await connmgr.accept(websocket)
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
        connmgr.disconnect(websocket)
    except ConnectionClosed:
        connmgr.disconnect(websocket)
