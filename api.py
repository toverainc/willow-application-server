import json
import os
import subprocess
import threading
from fastapi import Body, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect, WebSocketException, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from logging import getLogger
from requests import get
from shutil import move
from typing import Annotated, Dict
from websockets.exceptions import ConnectionClosed

from shared.was import (
    DIR_OTA,
    STORAGE_DEVICES,
    STORAGE_USER_CONFIG,
    STORAGE_USER_MULTINET,
    STORAGE_USER_NVS,
    construct_url,
    get_releases_gh,
)

app = FastAPI()
log = getLogger("WAS")
websocket = WebSocket


def migrate_user_files():
    for user_file in ['user_config.json', 'user_multinet.json', 'user_nvs.json']:
        if os.path.isfile(user_file):
            dest = f"storage/{user_file}"
            if not os.path.isfile(dest):
                move(user_file, dest)


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
        self.mac_addr = []
        self.ua = ua

    def set_hostname(self, hostname):
        self.hostname = hostname

    def set_hw_type(self, hw_type):
        self.hw_type = hw_type

    def set_mac_addr(self, mac_addr):
        self.mac_addr = mac_addr


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
        elif key == "mac_addr":
            self.connected_clients[ws].set_mac_addr(value)


if not os.path.isdir(DIR_OTA):
    os.makedirs(DIR_OTA)

app.mount("/ota", StaticFiles(directory=DIR_OTA), name="ota")
connmgr = ConnMgr()
releases = get_releases_gh()


def build_msg(config, container):
    try:
        msg = json.dumps({container: json.loads(config)}, sort_keys=True)
        return msg
    except Exception as e:
        log.error(f"failed to build config message: {e}")


def get_config_ws():
    config = None
    try:
        with open(STORAGE_USER_CONFIG, "r") as config_file:
            config = config_file.read()
    except Exception as e:
        log.error(f"failed to get config: {e}")
    finally:
        config_file.close()
        return config


def get_devices():
    devices = []

    if os.path.isfile(STORAGE_DEVICES):
        with open(STORAGE_DEVICES, "r") as devices_file:
            devices = json.load(devices_file)
        devices_file.close()
    else:
        with open(STORAGE_DEVICES, "x") as devices_file:
            json.dump(devices, devices_file)
        devices_file.close()

    return devices


def get_json_from_file(path):
    try:
        with open(path, "r") as file:
            data = json.load(file)
        file.close()
    except Exception:
        data = {}

    return JSONResponse(content=data)


async def post_config(request, apply=False):
    data = await request.json()
    if 'hostname' in data:
        hostname = data["hostname"]
        data = await get_config()
        data = json.loads(data.body)
        msg = build_msg(json.dumps(data), "config")
        try:
            ws = connmgr.get_client_by_hostname(hostname)
            await ws.send_text(msg)
            return "Success"
        except Exception as e:
            log.error(f"failed to apply config to {data['hostname']} ({e})")
            return "Error"
    else:
        save_json_to_file(STORAGE_USER_CONFIG, data)
        msg = build_msg(data, "config")
        log.info(str(msg))
        if apply:
            await connmgr.broadcast(websocket, msg)
        return "Success"


async def post_nvs(request, apply=False):
    data = await request.json()
    if 'hostname' in data:
        hostname = data["hostname"]
        data = await get_nvs()
        data = json.loads(data.body)
        msg = build_msg(json.dumps(data), "nvs")
        try:
            ws = connmgr.get_client_by_hostname(hostname)
            await ws.send_text(msg)
            return "Success"
        except Exception as e:
            log.error(f"failed to apply config to {data['hostname']} ({e})")
            return "Error"
    else:
        save_json_to_file(STORAGE_USER_NVS, data)
        msg = build_msg(data, "nvs")
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
    migrate_user_files()
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
            'mac_addr': client.mac_addr,
            'ip': ws.client.host,
            'port': ws.client.port,
            'user_agent': client.ua
        })

    return JSONResponse(content=clients)


@app.get("/api/config")
async def get_config():
    return get_json_from_file(STORAGE_USER_CONFIG)


@app.get("/api/ha_token")
async def get_ha_token():
    try:
        resp = await get_config()
        config = json.loads(resp.body)
        return PlainTextResponse(config["hass_token"])
    except Exception as e:
        return str(e)


@app.get("/api/ha_url")
async def get_ha_url():
    try:
        resp = await get_config()
        config = json.loads(resp.body)
        url = construct_url(config["hass_host"], config["hass_port"], config["hass_tls"])
        return PlainTextResponse(url)
    except Exception as e:
        return str(e)


@app.get("/api/multinet")
async def get_multinet():
    return get_json_from_file(STORAGE_USER_MULTINET)


@app.get("/api/nvs")
async def get_nvs():
    return get_json_from_file(STORAGE_USER_NVS)


@app.get("/api/releases/")
async def api_get_releases(refresh=False):
    if refresh:
        releases = get_releases_gh()
    return releases


@app.post("/api/config/apply")
async def apply_config(request: Request):
    await post_config(request, True)


@app.post("/api/config/save")
async def save_config(request: Request):
    await post_config(request, False)


@app.post("/api/device")
async def post_device(request: Request):
    data = await request.json()

    devices = get_devices()
    new = True

    for i, device in enumerate(devices):
        if device.get("mac_addr") == data['mac_addr']:
            new = False
            devices[i] = data
            break

    if new and len(data['mac_addr']) > 0:
        devices.append(data)

    with open(STORAGE_DEVICES, "w") as devices_file:
        json.dump(devices, devices_file)
    devices_file.close()


@app.post("/api/nvs/apply")
async def apply_nvs(request: Request):
    await post_nvs(request, True)


@app.post("/api/nvs/save")
async def save_nvs(request: Request):
    await post_nvs(request, False)


@app.post("/api/release/cache")
async def post_release_cache(request: Request):
    data = await request.json()

    dir = f"./{DIR_OTA}/{data['version']}"
    if not os.path.isdir(dir):
        os.makedirs(dir)

    path = f"{dir}/{data['file_name']}"
    if os.path.exists(path):
        if os.path.getsize(path) == data['size']:
            return
        else:
            os.remove(path)

    resp = get(data['gh_url'])
    if resp.status_code == 200:
        with open(path, "wb") as fw:
            fw.write(resp.content)
        fw.close()
        return
    else:
        raise HTTPException(status_code=resp.status_code)


@app.post("/api/release/delete")
async def post_release_delete(request: Request):
    data = await request.json()
    os.remove(data['path'])


@app.post("/api/ota")
async def post_ota(body: Dict = Body(...)):
    log.error(f"body: {body} {type(body)}")
    msg = json.dumps({'cmd': 'ota_start', 'ota_url': body["ota_url"]})
    try:
        ws = connmgr.get_client_by_hostname(body["hostname"])
        await ws.send_text(msg)
    except Exception as e:
        log.error(f"failed to trigger OTA ({e})")


@app.websocket("/ws")
async def websocket_endpoint(
        websocket: websocket,
        user_agent: Annotated[str | None, Header(convert_underscores=True)] = None):
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
                if "mac_addr" in msg["hello"]:
                    connmgr.update_client(websocket, "mac_addr", msg["hello"]["mac_addr"])
            else:
                await connmgr.broadcast(websocket, data)
    except WebSocketDisconnect:
        connmgr.disconnect(websocket)
    except ConnectionClosed:
        connmgr.disconnect(websocket)
