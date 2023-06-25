import json, os
import subprocess
import threading
from fastapi import Body, FastAPI, Header, WebSocket, WebSocketDisconnect, WebSocketException, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from logging import getLogger
from typing import Annotated, Dict
from websockets.exceptions import ConnectionClosed

from shared.was import construct_url

app = FastAPI()
log = getLogger("WAS")
websocket = WebSocket

def start_ui():
    def run(job):
        proc = subprocess.Popen(job)
        proc.wait()
        return proc

    job = ['streamlit', 'run', 'ui.py']

    # server thread will remain active as long as FastAPI thread is running
    thread = threading.Thread(name='WAS UI', target=run, args=(job,), daemon=True)
    thread.start()

class Client:
    def __init__(self, ua):
        self.hostname = "unknown"
        self.hw_type = "unknown"
        self.ua = ua

    def set_hostname(self, hostname):
        self.hostname = hostname

    def set_hw_type(self, hw_type):
        self.hw_type = hw_type


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

    def get_client_by_hostname(self, hostname):
        for k, v in self.connected_clients.items():
            if v.hostname == hostname:
                return k

    def update_client(self, ws, key, value):
        if key == "hostname":
            self.connected_clients[ws].set_hostname(value)
        elif key == "hw_type":
            self.connected_clients[ws].set_hw_type(value)


app.mount("/static", StaticFiles(directory="static"), name="static")
connmgr = ConnMgr()


def build_msg(config, container):
    try:
        msg = json.dumps({container: json.loads(config)}, sort_keys=True)
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

def get_json_from_file(path):
    try:
        with open(path, "r") as file:
            data = json.load(file)
        file.close()
    except:
        data = {}

    return JSONResponse(content=data)

async def post_config(request, apply=False):
    data = await request.json()
    save_json_to_file("user_config.json", data)
    msg = build_msg(data, "config")
    log.info(str(msg))
    if apply:
        await connmgr.broadcast(websocket, msg)
    return "Success"

def save_json_to_file(path, content):
    with open(path, "w") as config_file:
        config_file.write(content)
    config_file.close()


@app.on_event("startup")
async def startup_event():
    start_ui()

@app.get("/")
def read_root():
    return {"Hello": "World"}

@app.get("/api/clients")
async def get_clients():
    clients = []
    for ws, client in connmgr.connected_clients.items():
        clients.append({
            'hostname': client.hostname,
            'hw_type': client.hw_type,
            'ip': ws.client.host,
            'port': ws.client.port,
            'user_agent': client.ua
        })

    return JSONResponse(content=clients)

@app.get("/api/config")
async def get_config():
    return get_json_from_file("user_config.json")

@app.get("/api/ha_url")
async def get_ha_url():
    try:
        resp = await get_config()
        config = json.loads(resp.body)
        url = construct_url(config["hass_host"], config["hass_port"], config["hass_tls"])
        return PlainTextResponse(url)
    except Exception as e:
        return str(e)

@app.get("/api/nvs")
async def get_nvs():
    return get_json_from_file("user_nvs.json")

@app.post("/api/config/apply")
async def apply_config(request: Request):
    await post_config(request, True)

@app.post("/api/config/save")
async def save_config(request: Request):
    await post_config(request, False)

@app.post("/api/nvs")
async def post_nvs(request: Request):
    data = await request.json()
    save_json_to_file("user_nvs.json", data)
    msg = build_msg(data, "nvs")
    log.info(str(msg))
    await connmgr.broadcast(websocket, msg)
    return "Success"

@app.post("/api/ota")
async def post_ota(body: Dict = Body(...)):
    log.error(f"body: {body} {type(body)}")
    msg = json.dumps({'cmd':'ota_start', 'ota_url': os.environ['OTA_URL']})
    try:
        ws = connmgr.get_client_by_hostname(body["hostname"])
        await ws.send_text(msg)
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
                    await websocket.send_text(build_msg(get_config_ws(), "config"))

            elif "hello" in msg:
                if "hostname" in msg["hello"]:
                    connmgr.update_client(websocket, "hostname", msg["hello"]["hostname"])
                if "hw_type" in msg["hello"]:
                    connmgr.update_client(websocket, "hw_type", msg["hello"]["hw_type"])

            else:
                await connmgr.broadcast(websocket, data)
    except WebSocketDisconnect:
        connmgr.disconnect(websocket)
    except ConnectionClosed:
        connmgr.disconnect(websocket)
