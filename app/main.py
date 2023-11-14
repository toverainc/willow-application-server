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
)
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
import logging
import magic
from pathlib import Path
import random
import time
from requests import get
from shutil import move
from typing import Annotated
from websockets.exceptions import ConnectionClosed
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Literal

from app.const import (
    DIR_ASSET,
    DIR_OTA,
    STORAGE_USER_CONFIG,
    STORAGE_USER_NVS,
    STORAGE_USER_WAS,
    URL_WILLOW_RELEASES,
)
from app.internal.command_endpoints.ha_rest import HomeAssistantRestEndpoint
from app.internal.command_endpoints.ha_ws import (
    HomeAssistantWebSocketEndpoint,
    HomeAssistantWebSocketEndpointNotSupportedException
)
from app.internal.command_endpoints.mqtt import MqttConfig, MqttEndpoint
from app.internal.command_endpoints.openhab import OpenhabEndpoint
from app.internal.command_endpoints.rest import RestEndpoint

from app.internal.was import (
    get_config,
    get_nvs,
    get_release_url,
    get_tz_config,
)

from .internal.client import Client
from .internal.connmgr import ConnMgr
from .internal.notify import NotifyQueue
from .internal.wake import WakeEvent, WakeSession
from .routers import client
from .routers import config
from .routers import status


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


# Make sure we always have DIR_OTA
Path(DIR_OTA).mkdir(parents=True, exist_ok=True)


app.mount("/admin", StaticFiles(directory="static/admin", html=True), name="admin")


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
            log.error(f"Failed to apply config to {hostname} ({e})")
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
            log.error(f"Failed to apply config to {hostname} ({e})")
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

        elif user_config["command_endpoint"] == "MQTT":
            mqtt_config = MqttConfig()
            mqtt_config.set_auth_type(user_config["mqtt_auth_type"])
            mqtt_config.set_hostname(user_config["mqtt_host"])
            mqtt_config.set_port(user_config["mqtt_port"])
            mqtt_config.set_tls(user_config["mqtt_tls"])
            mqtt_config.set_topic(user_config["mqtt_topic"])

            if 'mqtt_password' in user_config:
                mqtt_config.set_password(user_config['mqtt_password'])

            if 'mqtt_username' in user_config:
                mqtt_config.set_username(user_config['mqtt_username'])

            app.command_endpoint = MqttEndpoint(mqtt_config)

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

    app.connmgr = ConnMgr()

    try:
        init_command_endpoint(app)
    except Exception as e:
        app.command_endpoint = None
        log.error(f"failed to initialize command endpoint ({e})")

    app.notify_queue = NotifyQueue(connmgr=app.connmgr)
    app.notify_queue.start()


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


app.include_router(client.router)

app.include_router(config.router)

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


app.include_router(status.router)


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

    await app.connmgr.accept(websocket, client)
    try:
        while True:
            data = await websocket.receive_text()
            log.debug(str(data))
            msg = json.loads(data)

            # latency sensitive so handle first
            if "wake_start" in msg:
                global wake_session
                if wake_session is not None:
                    if wake_session.done:
                        del wake_session
                        wake_session = WakeSession()
                        asyncio.create_task(wake_session.cleanup())
                else:
                    wake_session = WakeSession()
                    asyncio.create_task(wake_session.cleanup())

                if "wake_volume" in msg["wake_start"]:
                    wake_event = WakeEvent(websocket, msg["wake_start"]["wake_volume"])
                    wake_session.add_event(wake_event)

            elif "wake_end" in msg:
                pass

            elif "notify_done" in msg:
                app.notify_queue.done(websocket, msg["notify_done"])

            elif "cmd" in msg:
                if msg["cmd"] == "endpoint":
                    if app.command_endpoint is not None:
                        log.debug(f"Sending {msg['data']} to {app.command_endpoint.name}")
                        resp = app.command_endpoint.send(jsondata=msg["data"], ws=websocket)
                        if resp is not None:
                            resp = app.command_endpoint.parse_response(resp)
                            log.debug(f"Got response {resp} from endpoint")
                            # HomeAssistantWebSocketEndpoint sends message via callback
                            if resp is not None:
                                asyncio.ensure_future(websocket.send_text(resp))

                elif msg["cmd"] == "get_config":
                    asyncio.ensure_future(websocket.send_text(build_msg(get_config_ws(), "config")))

            elif "goodbye" in msg:
                app.connmgr.disconnect(websocket)

            elif "hello" in msg:
                if "hostname" in msg["hello"]:
                    app.connmgr.update_client(websocket, "hostname", msg["hello"]["hostname"])
                if "hw_type" in msg["hello"]:
                    platform = msg["hello"]["hw_type"].upper()
                    app.connmgr.update_client(websocket, "platform", platform)
                if "mac_addr" in msg["hello"]:
                    mac_addr = hex_mac(msg["hello"]["mac_addr"])
                    app.connmgr.update_client(websocket, "mac_addr", mac_addr)

    except WebSocketDisconnect:
        app.connmgr.disconnect(websocket)
    except ConnectionClosed:
        app.connmgr.disconnect(websocket)
