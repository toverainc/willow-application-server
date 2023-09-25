import asyncio
from hashlib import sha256
import json
import os
from fastapi import FastAPI, Depends, Header, HTTPException, WebSocket, WebSocketDisconnect, WebSocketException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
import logging
from pathlib import Path
import random
import time
from requests import get
from shutil import move
from typing import Annotated, Dict
from uuid import uuid4
from websockets.exceptions import ConnectionClosed
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Literal

from shared.was import (
    DIR_OTA,
    STORAGE_USER_CLIENT_CONFIG,
    STORAGE_USER_CONFIG,
    STORAGE_USER_MULTINET,
    STORAGE_USER_NVS,
    URL_WILLOW_RELEASES,
    construct_url,
    get_release_url,
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
wake_session = None
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

def is_safe_path(basedir, path, follow_symlinks=True):
    # resolves symbolic links
    if follow_symlinks:
        matchpath = os.path.realpath(path)
    else:
        matchpath = os.path.abspath(path)
    return basedir == os.path.commonpath((basedir, matchpath))

class Client:
    def __init__(self, ua):
        self.hostname = "unknown"
        self.platform = "unknown"
        self.mac_addr = []
        self.ua = ua

    def set_hostname(self, hostname):
        self.hostname = hostname

    def set_platform(self, platform):
        self.platform = platform

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
        elif key == "platform":
            self.connected_clients[ws].set_platform(value)
        elif key == "mac_addr":
            self.connected_clients[ws].set_mac_addr(value)

class WakeEvent:
    def __init__(self, client, volume):
        self.client = client
        self.volume = volume

class WakeSession:
    def __init__(self):
        self.events = []
        self.id = uuid4()
        self.ts = time.time()
        log.error(f"WakeSession with ID {self.id} created")

    def add_event(self, event):
        log.error(f"WakeSession {self.id} adding event {event}")
        self.events.append(event)

    async def cleanup(self, timeout=200):
        await asyncio.sleep(timeout / 1000)
        max_volume = -1000.0
        winner = None
        for event in self.events:
            if event.volume > max_volume:
                max_volume = event.volume
                winner = event.client

        # notify winner first
        await winner.send_text(json.dumps({'wake_result': {'won': True}}))

        for event in self.events:
            if event.client != winner:
                await event.client.send_text(json.dumps({'wake_result': {'won': False}}))

        log.error(f"Terminating WakeSession with ID {self.id}. Winner: {winner}")
        global wake_session
        wake_session = None



# Make sure we always have DIR_OTA
Path(DIR_OTA).mkdir(parents=True, exist_ok=True)


app.mount("/admin", StaticFiles(directory="static/admin", html=True), name="admin")
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

    if os.path.isfile(STORAGE_USER_CLIENT_CONFIG):
        with open(STORAGE_USER_CLIENT_CONFIG, "r") as devices_file:
            devices = json.load(devices_file)
        devices_file.close()
    else:
        with open(STORAGE_USER_CLIENT_CONFIG, "x") as devices_file:
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


def get_config():
    return get_json_from_file(STORAGE_USER_CONFIG)


def get_multinet():
    return get_json_from_file(STORAGE_USER_MULTINET)


def get_nvs():
    return get_json_from_file(STORAGE_USER_NVS)


def get_was_url():
    try:
        nvs = get_nvs()
        return nvs["WAS"]["URL"]
    except Exception:
        return False


# TODO: Find a better way but we need to handle every error possible
def get_releases_local():
    local_dir = f"{DIR_OTA}/local"
    assets = []
    if not os.path.exists(local_dir):
        return assets

    url = "https://heywillow.io"

    for asset_name in os.listdir(local_dir):
        if '.bin' in asset_name:
            file = f"{DIR_OTA}/local/{asset_name}"
            created_at = os.path.getctime(file)
            created_at = time.ctime(created_at)
            created_at = time.strptime(created_at)
            created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", created_at)
            with open(file,"rb") as f:
                bytes = f.read()
                checksum = sha256(bytes).hexdigest()
            asset = {}
            asset["name"] = f"willow-ota-{asset_name}"
            asset["tag_name"] = f"willow-ota-{asset_name}"
            asset["platform"] = asset_name.replace('.bin', '')
            asset["platform_name"] = asset["platform"]
            asset["platform_image"] = "https://heywillow.io/images/esp32_s3_box.png"
            asset["build_type"] = "ota"
            asset["url"] = url
            asset["id"] = random.randint(10, 99)
            asset["content_type"] = "raw"
            asset["size"] = os.path.getsize(file)
            asset["created_at"] = created_at
            asset["browser_download_url"] = url
            asset["sha256"] = checksum
            assets.append(asset)

    if assets == []:
        return []
    else:
        return [{"name": "local",
                 "tag_name": "local",
                 "id": random.randint(10, 99),
                 "url": url,
                 "html_url": url,
                 "assets": assets}]


def get_releases_willow():
    releases = get(URL_WILLOW_RELEASES)
    releases = releases.json()
    try:
        releases_local = get_releases_local()
    except:
        pass
    else:
        releases = releases_local + releases
    return releases

async def post_config(request, apply=False):
    data = await request.json()
    if 'hostname' in data:
        hostname = data["hostname"]
        data = get_config()
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
        data = get_nvs()
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
def api_redirect_admin():
    return "/admin"


@app.get("/api/client")
async def api_get_client():
    devices = get_devices()
    clients = []
    macs = []
    labels = {}

    # This is ugly but it provides a combined response
    for ws, client in connmgr.connected_clients.items():
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

    return JSONResponse(content=clients)


class GetConfig(BaseModel):
    type: Literal['config', 'nvs', 'ha_url', 'ha_token', 'multinet'] = Field (Query(..., description='Configuration type'))


@app.get("/api/config")
async def api_get_config(config: GetConfig = Depends()):
    if config.type == "nvs":
        nvs = get_nvs()
        return JSONResponse(content=nvs)
    elif config.type == "config":
        config = get_config()
        return JSONResponse(content=config)
    elif config.type == "ha_token":
        config = get_config()
        return PlainTextResponse(config["hass_token"])
    elif config.type == "ha_url":
        config = get_config()
        url = construct_url(config["hass_host"], config["hass_port"], config["hass_tls"])
        return PlainTextResponse(url)
    elif config.type == "multinet":
        config = get_multinet()
        return JSONResponse(content=config)

@app.get("/api/ota")
async def api_get_ota(version: str, platform: str):
    ota_file = f"{DIR_OTA}/{version}/{platform}.bin"
    if not is_safe_path(DIR_OTA, ota_file):
        return
    if not os.path.isfile(ota_file):
        releases = get_releases_willow()
        for release in releases:
            if release["name"] == version:
                assets = release["assets"]
                for asset in assets:
                    if asset["platform"] == platform:
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
                    platform = asset["platform"]
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
async def api_apply_config(request: Request, config: PostConfig = Depends()):
    if config.type == "config":
        await post_config(request, config.apply)
    elif config.type == "nvs":
        await post_nvs(request, config.apply)


class PostClient(BaseModel):
    action: Literal['restart', 'update', 'config'] = Field (Query(..., description='Client action'))


@app.post("/api/client")
async def api_post_client(request: Request, device: PostClient = Depends()):
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

        with open(STORAGE_USER_CLIENT_CONFIG, "w") as devices_file:
            json.dump(devices, devices_file)
        devices_file.close()


class PostRelease(BaseModel):
    action: Literal['cache', 'delete'] = Field (Query(..., description='Release Cache Control'))


@app.post("/api/release")
async def api_post_release(request: Request, release: PostRelease = Depends()):
    if release.action == "cache":
        data = await request.json()

        dir = f"{DIR_OTA}/{data['version']}"
        # Check for safe path
        if not is_safe_path(DIR_OTA, dir):
            return
        Path(dir).mkdir(parents=True, exist_ok=True)

        path = f"{dir}/{data['platform']}.bin"
        if os.path.exists(path):
            if os.path.getsize(path) == data['size']:
                return
            else:
                os.remove(path)

        resp = get(data['willow_url'])
        if resp.status_code == 200:
            with open(path, "wb") as fw:
                fw.write(resp.content)
            return
        else:
            raise HTTPException(status_code=resp.status_code)
    elif release.action == "delete":
        data = await request.json()
        path = data['path']
        if is_safe_path(DIR_OTA, path):
            os.remove(path)


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

            # latency sensitive so handle first
            if "wake_start" in msg:
                global wake_session
                if wake_session is None:
                    wake_session = WakeSession()
                    asyncio.create_task(wake_session.cleanup())
                if "wake_volume" in msg["wake_start"]:
                    wake_event = WakeEvent(websocket, msg["wake_start"]["wake_volume"])
                    wake_session.add_event(wake_event)

            elif "wake_end" in msg:
                pass

            if "cmd" in msg:
                if msg["cmd"] == "get_config":
                    await websocket.send_text(build_msg(get_config_ws(), "config"))

            elif "hello" in msg:
                if "hostname" in msg["hello"]:
                    connmgr.update_client(websocket, "hostname", msg["hello"]["hostname"])
                if "hw_type" in msg["hello"]:
                    platform = msg["hello"]["hw_type"].upper()
                    connmgr.update_client(websocket, "platform", platform)
                if "mac_addr" in msg["hello"]:
                    mac_addr = hex_mac(msg["hello"]["mac_addr"])
                    connmgr.update_client(websocket, "mac_addr", mac_addr)
            else:
                await connmgr.broadcast(websocket, data)
    except WebSocketDisconnect:
        connmgr.disconnect(websocket)
    except ConnectionClosed:
        connmgr.disconnect(websocket)
