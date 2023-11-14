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
    DIR_OTA,
    STORAGE_USER_CONFIG,
    URL_WILLOW_RELEASES,
)

from app.internal.command_endpoints.main import init_command_endpoint
from app.internal.was import (
    build_msg,
    get_nvs,
    get_release_url,
    get_tz_config,
    is_safe_path,
)

from .internal.client import Client
from .internal.connmgr import ConnMgr
from .internal.notify import NotifyQueue
from .internal.wake import WakeEvent, WakeSession
from .routers import asset
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


# Make sure we always have DIR_OTA
Path(DIR_OTA).mkdir(parents=True, exist_ok=True)


app.mount("/admin", StaticFiles(directory="static/admin", html=True), name="admin")


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


app.include_router(asset.router)


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
