import json
import magic
import os
import random
import re
import requests
import socket
import time
import urllib
import urllib3

from hashlib import sha256
from logging import getLogger

from num2words import num2words
from websockets.sync.client import connect

from app.db.main import get_config_db, get_nvs_db, save_config_to_db, save_nvs_to_db

from ..const import (
    DIR_OTA,
    STORAGE_TZ,
    STORAGE_USER_CLIENT_CONFIG,
    STORAGE_USER_CONFIG,
    STORAGE_USER_MULTINET,
    STORAGE_USER_NVS,
    STORAGE_USER_WAS,
    URL_WILLOW_RELEASES,
    URL_WILLOW_TZ,
)


log = getLogger("WAS")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def build_msg(config, container):
    try:
        msg = json.dumps({container: config}, sort_keys=True)
        return msg
    except Exception as e:
        log.error(f"Failed to build config message: {e}")


def construct_url(host, port, tls=False, ws=False):
    if tls:
        if ws:
            scheme = "wss"
        else:
            scheme = "https"
    else:
        if ws:
            scheme = "ws"
        else:
            scheme = "http"

    return f"{scheme}://{host}:{port}"


def construct_wis_tts_url(url):
    parsed = urllib.parse.urlparse(url)
    if len(parsed.query) == 0:
        return urllib.parse.urljoin(url, "?text=")
    else:
        params = urllib.parse.parse_qs(parsed.query)
        log.debug(f"construct_wis_tts_url: parsed={parsed} - params={params}")
        if "text" in params:
            log.warning("removing text parameter from WIS TTS URL")
            del params["text"]
        params["text"] = ""
        parsed = parsed._replace(query=urllib.parse.urlencode(params, doseq=True))
        log.debug(f"construct_wis_tts_url: parsed={parsed} - params={params}")
        return urllib.parse.urlunparse(parsed)


async def device_command(connmgr, data, command):
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


def do_get_request(url, verify=False, timeout=(1, 60)):
    try:
        parsed_url = urllib.parse.urlparse(url)

        if parsed_url.username and parsed_url.password:
            # Request with auth
            basic_auth = requests.auth.HTTPBasicAuth(parsed_url.username, parsed_url.password)
            response = requests.get(url, verify=verify, timeout=timeout, auth=basic_auth)
        else:
            # Request without auth
            response = requests.get(url, verify=verify, timeout=timeout)
        return response

    except Exception as e:
        print(f"An error occurred: {str(e)}")
        return None


def get_config():
    return get_json_from_file(STORAGE_USER_CONFIG)


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


def get_ha_commands_for_entity(entity):
    commands = []
    pattern = r'[^A-Za-z- ]'

    numbers = re.search(r'(\d{1,})', entity)
    if numbers:
        for number in numbers.groups():
            entity = entity.replace(number, f" {num2words(int(number))} ")

    entity = entity.replace('_', ' ')
    entity = re.sub(pattern, '', entity)
    entity = " ".join(entity.split())
    entity = entity.upper()

    on = f'TURN ON {entity}'
    off = f'TURN OFF {entity}'

    # ESP_MN_MAX_PHRASE_LEN=63
    if len(off) < 63:
        commands.extend([on, off])

    return commands


def get_ha_entities(url, token):
    if token is None:
        return json.dumps({'error': 'HA token not set'})

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    url = f"{url}/api/states"
    response = requests.get(url, headers=headers)
    data = response.json()
    data.sort(key=lambda x: x['entity_id'])
    return data


def get_ip():
    sk = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sk.connect(("1.1.1.1", 53))
    ip = sk.getsockname()[0]
    sk.close()
    return ip


def get_json_from_file(path):
    try:
        with open(path, "r") as file:
            data = json.load(file)
        file.close()
    except Exception:
        data = {}

    return data


def get_mime_type(filename):
    mime_type = magic.Magic(mime=True).from_file(filename)
    return mime_type


def get_multinet():
    return get_json_from_file(STORAGE_USER_MULTINET)


def get_nvs():
    return get_json_from_file(STORAGE_USER_NVS)


def get_release_url(was_url, version, platform):
    #url_parts = re.match(r"^(?:\w+:\/\/)?([^\/:]+)(?::(\d+))?", was_url)
    parsed = urllib.parse.urlparse(was_url)

    match parsed.scheme:
        case "ws":
            scheme = "http"
        case "wss":
            scheme = "https"

    url = f"{scheme}://{parsed.netloc}/api/ota?version={version}&platform={platform}"
    return url


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
            with open(file, "rb") as f:
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
    releases = requests.get(URL_WILLOW_RELEASES)
    releases = releases.json()
    try:
        releases_local = get_releases_local()
    except Exception:
        pass
    else:
        releases = releases_local + releases
    return releases


def get_tz():
    try:
        with open("tz.json", "r") as config_file:
            tz = json.load(config_file)
        config_file.close()
    except Exception:
        tz = {}

    return tz


def get_tz_config(refresh=False):
    if refresh:
        tz = requests.get(URL_WILLOW_TZ).json()
        with open(STORAGE_TZ, "w") as tz_file:
            json.dump(tz, tz_file)
        tz_file.close()

    return get_json_from_file(STORAGE_TZ)


def get_was_config():
    return get_json_from_file(STORAGE_USER_WAS)


def get_was_url():
    try:
        nvs = get_nvs_db()
        return nvs["WAS"]["URL"]
    except Exception:
        return False


def is_safe_path(basedir, path, follow_symlinks=True):
    # resolves symbolic links
    if follow_symlinks:
        matchpath = os.path.realpath(path)
    else:
        matchpath = os.path.abspath(path)
    return basedir == os.path.commonpath((basedir, matchpath))


def merge_dict(dict_1, dict_2):
    result = dict_1 | dict_2
    return result


async def post_config(request, apply=False):
    data = await request.json()
    if 'hostname' in data:
        hostname = data["hostname"]
        data = get_config_db()
        msg = build_msg(data, "config")
        try:
            ws = request.app.connmgr.get_client_by_hostname(hostname)
            await ws.send_text(msg)
            return "Success"
        except Exception as e:
            log.error(f"Failed to apply config to {hostname} ({e})")
            return "Error"
    else:
        if "wis_tts_url" in data:
            data["wis_tts_url_v2"] = construct_wis_tts_url(data["wis_tts_url"])
            del data["wis_tts_url"]
            log.debug(f"wis_tts_url_v2: {data['wis_tts_url_v2']}")

        save_config_to_db(data)
        msg = build_msg(data, "config")
        log.debug(str(msg))
        if apply:
            await request.app.connmgr.broadcast(msg)
        return "Success"


async def post_nvs(request, apply=False):
    data = await request.json()
    if 'hostname' in data:
        hostname = data["hostname"]
        data = get_nvs_db()
        msg = build_msg(data, "nvs")
        try:
            ws = request.app.connmgr.get_client_by_hostname(hostname)
            await ws.send_text(msg)
            return "Success"
        except Exception as e:
            log.error(f"Failed to apply config to {hostname} ({e})")
            return "Error"
    else:
        save_nvs_to_db(data)
        msg = build_msg(data, "nvs")
        log.debug(str(msg))
        if apply:
            await request.app.connmgr.broadcast(msg)
        return "Success"


async def post_was(request, apply=False):
    data = await request.json()
    data = json.dumps(data)
    save_json_to_file(STORAGE_USER_WAS, data)
    return "Success"


def save_json_to_file(path, content):
    with open(path, "w") as config_file:
        config_file.write(content)
    config_file.close()


def warm_tts(data):
    try:
        if "/api/tts" in data["audio_url"]:
            do_get_request(data["audio_url"])
            log.debug("TTS ready - passing to clients")
    except Exception:
        pass
