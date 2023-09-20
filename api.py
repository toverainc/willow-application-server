import json
import os
from fastapi import FastAPI, Depends, Header, HTTPException, WebSocket, WebSocketDisconnect, WebSocketException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
import logging
from pathlib import Path
from requests import get
from shutil import move
from typing import Annotated, Dict
from websockets.exceptions import ConnectionClosed
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Literal

from shared.was import (
    DIR_OTA,
    STORAGE_DEVICES,
    STORAGE_USER_CONFIG,
    STORAGE_USER_MULTINET,
    STORAGE_USER_NVS,
    construct_url,
    get_release_url,
    get_releases_willow,
)

logging.basicConfig(
    format='%(asctime)s %(levelname)-8s %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S')

app = FastAPI(title="Willow Application Server",
              description="Willow Management API",
              version="0.1",
              openapi_url="/openapi.json",
              docs_url="/docs",
              redoc_url="/redoc")

log = logging.getLogger("WAS")
websocket = WebSocket

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def migrate_user_files():
    for user_file in ['user_config.json', 'user_multinet.json', 'user_nvs.json']:
        if os.path.isfile(user_file):
            dest = f"storage/{user_file}"
            if not os.path.isfile(dest):
                move(user_file, dest)

def hex_mac(mac):
    if type(mac) == list:
        mac = '%02x:%02x:%02x:%02x:%02x:%02x' % (mac[0], mac[1], mac[2], mac[3], mac[4], mac[5])
    return mac

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

# Make sure we always have DIR_OTA
Path(DIR_OTA).mkdir(parents=True, exist_ok=True)


app.mount("/admin", StaticFiles(directory="static/admin", html=True), name="admin")
#app.mount("/ota", StaticFiles(directory=DIR_OTA), name="ota")
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

async def restart_device(data):
    if 'hostname' in data:
        hostname = data["hostname"]

    msg = json.dumps({'cmd': 'restart'})
    try:
        ws = connmgr.get_client_by_hostname(hostname)
        await ws.send_text(msg)
        return "Success"
    except Exception as e:
        log.error(f"failed to send restart command to {data['hostname']} ({e})")
        return "Error"

def get_json_from_file(path):
    try:
        with open(path, "r") as file:
            data = json.load(file)
        file.close()
    except Exception:
        data = {}

    return data


def get_nvs():
    return get_json_from_file(STORAGE_USER_NVS)


def get_was_url():
    try:
        nvs = get_nvs()
        return nvs["WAS"]["URL"]
    except Exception:
        return False


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
        data = json.dumps(data)
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
        data = json.dumps(data)
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


@app.get("/", response_class=RedirectResponse)
def redirect_admin():
    return "/admin"


@app.get("/api/client")
async def get_client():
    clients = []
    for ws, client in connmgr.connected_clients.items():
        mac_addr = hex_mac(client.mac_addr)
        clients.append({
            'hostname': client.hostname,
            'hw_type': client.hw_type,
            'mac_addr': mac_addr,
            'ip': ws.client.host,
            'port': ws.client.port,
            'user_agent': client.ua
        })

    return JSONResponse(content=clients)


class GetConfig(BaseModel):
    type: Literal['config', 'nvs'] = Field (Query(..., description='Configuration type'))


@app.get("/api/config")
async def get_config(config: GetConfig = Depends()):
    if config.type == "nvs":
        nvs = get_nvs()
        return JSONResponse(content=nvs)
    elif config.type == "config":
        config = get_json_from_file(STORAGE_USER_CONFIG)
        return JSONResponse(content=config)


@app.get("/api/device")
async def api_get_device():
    devices = get_devices()
    for device in devices:
        mac_addr = hex_mac(device['mac_addr'])
        device['mac_addr'] = mac_addr
    return JSONResponse(devices)


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
    multinet = get_json_from_file(STORAGE_USER_MULTINET)
    return JSONResponse(content=multinet)


@app.get("/api/ota")
async def get_ota(version: str, platform: str):
    ota_file = f"{DIR_OTA}/{version}/{platform}.bin"
    if not os.path.isfile(ota_file):
        releases = get_releases_willow()
        for release in releases:
            if release["name"] == version:
                assets = release["assets"]
                for asset in assets:
                    if asset["hw_type"] == platform:
                        Path(f"{DIR_OTA}/{version}").mkdir(parents=True, exist_ok=True)
                        r = get(asset["browser_download_url"])
                        open(ota_file, 'wb').write(r.content)

    return FileResponse(ota_file)

class GetRelease(BaseModel):
    type: Literal['was', 'willow'] = Field (Query(..., description='Release type'))

@app.get("/api/release")
async def api_get_release(release: GetRelease = Depends()):
    log.info('Got release request')
    releases = get_releases_willow()
    if release.type == "willow":
        return releases
    elif release.type == "was":
        was_url = get_was_url()
        if not was_url:
            raise HTTPException(status_code=500, detail="WAS URL not set")

        try:
            for release in releases:
                tag_name = release["tag_name"]
                assets = release["assets"]
                for asset in assets:
                    platform = asset["hw_type"]
                    asset["was_url"] = get_release_url(was_url, tag_name, platform)
                    if os.path.isfile(f"{DIR_OTA}/{tag_name}/{platform}.bin"):
                        asset["cached"] = True
                    else:
                        asset["cached"] = False
        except Exception as e:
            log.error(e)
            pass

        return JSONResponse(content=releases)

class PostConfig(BaseModel):
    type: Literal['config', 'nvs'] = Field (Query(..., description='Configuration type'))
    apply: bool = Field (Query(..., description='Apply configuration to device'))

@app.post("/api/config")
async def apply_config(request: Request, config: PostConfig = Depends()):
    if config.type == "config":
        await post_config(request, config.apply)
    elif type == "nvs":
        await post_nvs(request, config.apply)


class PostDevice(BaseModel):
    action: Literal['restart', 'update', 'config'] = Field (Query(..., description='Device action'))


@app.post("/api/device")
async def post_device(request: Request, device: PostDevice = Depends()):
    data = await request.json()

    if device.action == "restart":
        return await restart_device(data)
    elif device.action == "update":
        msg = json.dumps({'cmd': 'ota_start', 'ota_url': data["ota_url"]})
        try:
            ws = connmgr.get_client_by_hostname(data["hostname"])
            await ws.send_text(msg)
        except Exception as e:
            log.error(f"failed to trigger OTA ({e})")
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

        with open(STORAGE_DEVICES, "w") as devices_file:
            json.dump(devices, devices_file)
        devices_file.close()


class PostRelease(BaseModel):
    action: Literal['cache', 'delete'] = Field (Query(..., description='Release Cache Control'))


@app.post("/api/release")
async def post_release(request: Request, release: PostRelease = Depends()):
    if release.action == "cache":
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

        resp = get(data['willow_url'])
        if resp.status_code == 200:
            with open(path, "wb") as fw:
                fw.write(resp.content)
            fw.close()
            return
        else:
            raise HTTPException(status_code=resp.status_code)
    elif release.action == "delete":
        data = await request.json()
        os.remove(data['path'])


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
