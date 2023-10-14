import asyncio
from hashlib import sha256
import json
import os
from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Header,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
    WebSocketException,
)
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
import logging
import magic
from pathlib import Path
import random
import requests
import time
from requests import get
from shutil import move
from typing import Annotated, Dict
from uuid import uuid4
from websockets.exceptions import ConnectionClosed
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Literal, Optional

from command_endpoints.ha_rest import HomeAssistantRestEndpoint
from command_endpoints.ha_ws import HomeAssistantWebSocketEndpoint, HomeAssistantWebSocketEndpointNotSupportedException
from command_endpoints.openhab import OpenhabEndpoint
from command_endpoints.rest import RestEndpoint

from shared.was import (
    DIR_ASSET,
    DIR_OTA,
    STORAGE_USER_CLIENT_CONFIG,
    STORAGE_USER_CONFIG,
    STORAGE_USER_MULTINET,
    STORAGE_USER_NVS,
    STORAGE_USER_WAS,
    STORAGE_TZ,
    URL_WILLOW_RELEASES,
    URL_WILLOW_CONFIG,
    URL_WILLOW_TZ,
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
try:
    log.setLevel(os.environ.get("WAS_LOG_LEVEL").upper())
except:
    pass

wake_session = None

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_mime_type(filename):
    mime_type = magic.Magic(mime=True).from_file(filename)
    return mime_type


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
        self.mac_addr = "unknown"
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
            log.error(f"Failed to accept websocket connection: {e}")

    async def broadcast(self, msg: str):
        for client in self.connected_clients:
            try:
                await client.send_text(msg)
            except WebSocketException as e:
                log.error(f"Failed to broadcast message: {e}")

    def disconnect(self, ws: WebSocket):
        if ws in self.connected_clients:
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
        log.debug(f"WakeSession with ID {self.id} created")

    def add_event(self, event):
        log.debug(f"WakeSession {self.id} adding event {event}")
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

        log.debug(f"Terminating WakeSession with ID {self.id}. Winner: {winner}")
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
        log.error(f"Failed to build config message: {e}")


def get_config_ws():
    config = None
    try:
        with open(STORAGE_USER_CONFIG, "r") as config_file:
            config = config_file.read()
    except Exception as e:
        log.error(f"Failed to get config: {e}")
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


async def device_command(data, command):
    if 'hostname' in data:
        hostname = data["hostname"]

    msg = json.dumps({'cmd': command})
    try:
        ws = connmgr.get_client_by_hostname(hostname)
        await ws.send_text(msg)
        return "Success"
    except Exception as e:
        log.error(f"Failed to send restart command to {data['hostname']} ({e})")
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


def get_was_config():
    return get_json_from_file(STORAGE_USER_WAS)


def get_tz_config(refresh = False):
    if refresh:
        tz = get(URL_WILLOW_TZ).json()
        with open(STORAGE_TZ, "w") as tz_file:
            json.dump(tz, tz_file)
        tz_file.close()

    return get_json_from_file(STORAGE_TZ)


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
            log.error(f"Failed to apply config to {data['hostname']} ({e})")
            return "Error"
    else:
        data = json.dumps(data)
        save_json_to_file(STORAGE_USER_CONFIG, data)
        msg = build_msg(data, "config")
        log.debug(str(msg))
        if apply:
            await connmgr.broadcast(msg)
        return "Success"


async def post_was(request, apply=False):
    data = await request.json()
    data = json.dumps(data)
    save_json_to_file(STORAGE_USER_WAS, data)
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
            log.error(f"Failed to apply config to {data['hostname']} ({e})")
            return "Error"
    else:
        data = json.dumps(data)
        save_json_to_file(STORAGE_USER_NVS, data)
        msg = build_msg(data, "nvs")
        log.debug(str(msg))
        if apply:
            await connmgr.broadcast(msg)
        return "Success"


def save_json_to_file(path, content):
    with open(path, "w") as config_file:
        config_file.write(content)
    config_file.close()


def init_command_endpoint(app):
    # call command_endpoint.stop() to avoid leaking asyncio task
    try:
        app.command_endpoint.stop()
    except:
        pass

    user_config = get_config()

    if "was_mode" in user_config and user_config["was_mode"]:
        log.info("WAS Endpoint mode enabled")

        if user_config["command_endpoint"] == "Home Assistant":

            host = user_config["hass_host"]
            port = user_config["hass_port"]
            tls = user_config["hass_tls"]
            token = user_config["hass_token"]

            try:
                app.command_endpoint = HomeAssistantWebSocketEndpoint(app, host, port, tls, token)
            except HomeAssistantWebSocketEndpointNotSupportedException:
                app.command_endpoint = HomeAssistantRestEndpoint(host, port, tls, token)

        elif user_config["command_endpoint"] == "openHAB":
            app.command_endpoint = OpenhabEndpoint(user_config["openhab_url"], user_config["openhab_token"])

        elif user_config["command_endpoint"] == "REST":
            app.command_endpoint = RestEndpoint(user_config["rest_url"])
            app.command_endpoint.config.set_auth_type(user_config["rest_auth_type"])

            if "rest_auth_header" in user_config:
                app.command_endpoint.config.set_auth_header(user_config["rest_auth_header"])

            if "rest_auth_pass" in user_config:
                app.command_endpoint.config.set_auth_pass(user_config["rest_auth_pass"])

            if "rest_auth_user" in user_config:
                app.command_endpoint.config.set_auth_user(user_config["rest_auth_user"])


@app.on_event("startup")
async def startup_event():
    migrate_user_files()
    get_tz_config(refresh=True)

    init_command_endpoint(app)


@app.get("/", response_class=RedirectResponse)
def api_redirect_admin():
    log.debug('API GET ROOT: Request')
    return "/admin"


class GetAsset(BaseModel):
    asset: str = Field (Query(..., description='Asset'))
    type: Literal['audio', 'image', 'other'] = Field (Query(..., description='Asset type'))


@app.get("/api/asset")
async def api_get_asset(asset: GetAsset = Depends()):
    log.debug('API GET ASSET: Request')
    asset_file = f"{DIR_ASSET}/{asset.type}/{asset.asset}"
    if not is_safe_path(DIR_ASSET, asset_file):
        return

    # If we don't have the asset file return 404
    if not os.path.isfile(asset_file):
        raise HTTPException(status_code=404, detail="Asset File Not Found")

    # Use libmagic to determine MIME type to be really sure
    magic_mime_type = get_mime_type(asset_file)

    # Return image and other types
    if asset.type == "image" or asset.type == "other":
        return FileResponse(asset_file, media_type=magic_mime_type)

    # Only support audio formats supported by Willow
    if magic_mime_type == "audio/flac" or magic_mime_type == "audio/x-wav":
            return FileResponse(asset_file, media_type=magic_mime_type)
    else:
        raise HTTPException(status_code=404, detail="Audio Asset wrong file format")


@app.get("/api/client")
async def api_get_client():
    log.debug('API GET CLIENT: Request')
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

    # Sort connected clients by label if we have it
    # If all devices don't have labels we fall back to sorting by hostname
    try:
        sorted_clients = sorted(clients, key=lambda x: x['label'])
    except:
        sorted_clients = sorted(clients, key=lambda x: x['hostname'])

    return JSONResponse(content=sorted_clients)


class GetConfig(BaseModel):
    type: Literal['config', 'nvs', 'ha_url', 'ha_token', 'multinet', 'was', 'tz'] = Field (Query(..., description='Configuration type'))
    default: Optional[bool] = False


@app.get("/api/config")
async def api_get_config(config: GetConfig = Depends()):
    log.debug('API GET CONFIG: Request')
    # TZ is special
    if config.type == "tz":
        config = get_tz_config(refresh=config.default)
        return JSONResponse(content=config)

    # Otherwise handle other config types
    if config.default:
        default_config = requests.get(f"{URL_WILLOW_CONFIG}?type={config.type}").json()
        if type(default_config) == dict:
            return default_config
        else:
            raise HTTPException(status_code=400, detail="Invalid default config")

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
    elif config.type == "was":
        config = get_was_config()
        return JSONResponse(content=config)

class GetOta(BaseModel):
    version: str = Field (Query(..., description='OTA Version'))
    platform: str = Field (Query(..., description='OTA Platform'))


@app.get("/api/ota")
async def api_get_ota(ota: GetOta = Depends()):
    log.debug('API GET OTA: Request')
    ota_file = f"{DIR_OTA}/{ota.version}/{ota.platform}.bin"
    if not is_safe_path(DIR_OTA, ota_file):
        return
    if not os.path.isfile(ota_file):
        releases = get_releases_willow()
        for release in releases:
            if release["name"] == ota.version:
                assets = release["assets"]
                for asset in assets:
                    if asset["platform"] == ota.platform:
                        Path(f"{DIR_OTA}/{ota.version}").mkdir(parents=True, exist_ok=True)
                        r = get(asset["browser_download_url"])
                        open(ota_file, 'wb').write(r.content)

    # If we still don't have the file return 404 - the platform and/or version doesn't exist
    if not os.path.isfile(ota_file):
        raise HTTPException(status_code=404, detail="OTA File Not Found")

    return FileResponse(ota_file)


class GetRelease(BaseModel):
    type: Literal['was', 'willow'] = Field (Query(..., description='Release type'))


@app.get("/api/release")
async def api_get_release(release: GetRelease = Depends()):
    log.debug('API GET RELEASE: Request')
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

class GetStatus(BaseModel):
    type: Literal['asyncio_tasks'] = Field (Query(..., description='Status type'))


@app.get("/api/status")
async def api_get_status(status: GetStatus = Depends()):
    log.debug('API GET STATUS: Request')
    res = []

    if status.type == "asyncio_tasks":
        tasks = asyncio.all_tasks()
        for task in tasks:
            res.append(f"{task.get_name()}: {task.get_coro()}")

    return JSONResponse(res)


class PostConfig(BaseModel):
    type: Literal['config', 'nvs', 'was'] = Field (Query(..., description='Configuration type'))
    apply: bool = Field (Query(..., description='Apply configuration to device'))


@app.post("/api/config")
async def api_post_config(request: Request, config: PostConfig = Depends()):
    log.debug('API POST CONFIG: Request')
    if config.type == "config":
        await post_config(request, config.apply)
        init_command_endpoint(app)
    elif config.type == "nvs":
        await post_nvs(request, config.apply)
    elif config.type == "was":
        await post_was(request, config.apply)

class PostClient(BaseModel):
    action: Literal['restart', 'update', 'config', 'identify'] = Field (Query(..., description='Client action'))


@app.post("/api/client")
async def api_post_client(request: Request, device: PostClient = Depends()):
    log.debug('API POST CLIENT: Request')
    data = await request.json()

    if device.action == "update":
        msg = json.dumps({'cmd': 'ota_start', 'ota_url': data["ota_url"]})
        try:
            ws = connmgr.get_client_by_hostname(data["hostname"])
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
    else:
        # Catch all assuming anything else is a device command
        return await device_command(data, device.action)


class PostRelease(BaseModel):
    action: Literal['cache', 'delete'] = Field (Query(..., description='Release Cache Control'))


@app.post("/api/release")
async def api_post_release(request: Request, release: PostRelease = Depends()):
    log.debug('API POST RELEASE: Request')
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
        websocket: WebSocket,
        user_agent: Annotated[str | None, Header(convert_underscores=True)] = None):
    client = Client(user_agent)

    await connmgr.accept(websocket, client)
    try:
        while True:
            data = await websocket.receive_text()
            log.debug(str(data))
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

            elif "cmd" in msg:
                if msg["cmd"] == "endpoint":
                    if app.command_endpoint is not None:
                        log.debug(f"Sending {msg['data']} to {app.command_endpoint.name}")
                        data = {"hostname": client.hostname, "platform": client.platform, "mac_addr":client.mac_addr, **msg["data"]}
                        resp = app.command_endpoint.send(jsondata=data, ws=websocket)
                        if resp is not None:
                            resp = app.command_endpoint.parse_response(resp)
                            log.debug(f"Got response {resp} from endpoint")
                            # HomeAssistantWebSocketEndpoint sends message via callback
                            if resp is not None:
                                asyncio.ensure_future(websocket.send_text(resp))

                elif msg["cmd"] == "get_config":
                    asyncio.ensure_future(websocket.send_text(build_msg(get_config_ws(), "config")))

            elif "goodbye" in msg:
                connmgr.disconnect(websocket)

            elif "hello" in msg:
                if "hostname" in msg["hello"]:
                    connmgr.update_client(websocket, "hostname", msg["hello"]["hostname"])
                if "hw_type" in msg["hello"]:
                    platform = msg["hello"]["hw_type"].upper()
                    connmgr.update_client(websocket, "platform", platform)
                if "mac_addr" in msg["hello"]:
                    mac_addr = hex_mac(msg["hello"]["mac_addr"])
                    connmgr.update_client(websocket, "mac_addr", mac_addr)

    except WebSocketDisconnect:
        connmgr.disconnect(websocket)
    except ConnectionClosed:
        connmgr.disconnect(websocket)
