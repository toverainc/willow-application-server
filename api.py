import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, WebSocketException, Request
from logging import getLogger

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


@app.get("/")
def read_root():
    return {"Hello": "World"}

@app.post("/config")
async def post_config(request: Request):
    data = await request.json()
    msg = json.dumps({'config': json.loads(data)}, sort_keys=True)
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
            await connmgr.broadcast(websocket, data)
    except WebSocketDisconnect:
        connmgr.disconnect(websocket)
