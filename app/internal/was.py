import json
import os
import re
import requests
import socket
import urllib
import urllib3

from logging import getLogger

from num2words import num2words
from websockets.sync.client import connect

from ..const import (
    STORAGE_TZ,
    STORAGE_USER_CLIENT_CONFIG,
    STORAGE_USER_CONFIG,
    STORAGE_USER_MULTINET,
    STORAGE_USER_NVS,
    STORAGE_USER_WAS,
    URL_WILLOW_TZ,
)


log = getLogger("WAS")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def build_msg(config, container):
    try:
        msg = json.dumps({container: json.loads(config)}, sort_keys=True)
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


def get_multinet():
    return get_json_from_file(STORAGE_USER_MULTINET)


def get_nvs():
    return get_json_from_file(STORAGE_USER_NVS)


# TODO: Support HTTPs
def get_release_url(was_url, version, platform):
    url_parts = re.match(r"^(?:\w+:\/\/)?([^\/:]+)(?::(\d+))?", was_url)
    host = url_parts.group(1)
    port = url_parts.group(2)
    url = f"http://{host}:{port}/api/ota?version={version}&platform={platform}"
    return url


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


def merge_dict(dict_1, dict_2):
    result = dict_1 | dict_2
    return result


async def post_config(request, apply=False):
    data = await request.json()
    if 'hostname' in data:
        hostname = data["hostname"]
        data = get_config()
        msg = build_msg(json.dumps(data), "config")
        try:
            ws = request.app.connmgr.get_client_by_hostname(hostname)
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
            await request.app.connmgr.broadcast(msg)
        return "Success"


async def post_nvs(request, apply=False):
    data = await request.json()
    if 'hostname' in data:
        hostname = data["hostname"]
        data = get_nvs()
        msg = build_msg(json.dumps(data), "nvs")
        try:
            ws = request.app.connmgr.get_client_by_hostname(hostname)
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


def test_url(url, error_msg, ws=False):
    ok = True
    try:
        if ws:
            conn = connect(url)
            conn.close()
            ok = True
        else:
            requests.get(url)
            ok = True
    except Exception:
        ok = False

    if ok:
        return True
    else:
        #st.write(f":red[{error_msg}]")
        return False


def validate_config(config, skip_check = False):
    ok = True
    if config['command_endpoint'] == 'Home Assistant':
        if not validate_string(config['hass_token'], "Invalid Home Assistant token", 1):
            ok = False
        ha_url = construct_url(config["hass_host"], config["hass_port"], config["hass_tls"])
        if not skip_check:
            if not test_url(ha_url, f":red[Unable to reach Home Assistant on {ha_url}]"):
                ok = False
    elif config['command_endpoint'] == 'openHAB':
        if not validate_url(config['openhab_url']):
            ok = False
        elif not skip_check:
            if not test_url(config['openhab_url'], f":red[Unable to reach openHAB on {config['openhab_url']}]"):
                ok = False
    elif config['command_endpoint'] == 'REST':
        if config['rest_auth_type'] == 'Basic':
            if not validate_string(config['rest_auth_pass'], "Invalid REST auth password", 1):
                ok = False
            if not validate_string(config['rest_auth_user'], "Invalid REST auth username", 1):
                ok = False
        elif config['rest_auth_type'] == 'Header':
            if not validate_string(config['rest_auth_header'], "Invalid REST auth header", 1):
                ok = False
        if not validate_url(config['rest_url']):
            ok = False
        elif not skip_check:
            if not test_url(config['rest_url'], f":red[Unable to reach REST endpoint on {config['rest_url']}]"):
                ok = False
    if config['speech_rec_mode']:
        if not validate_url(config['wis_tts_url']):
            ok = False
    if not validate_url(config['wis_url']):
        ok = False
    return ok


def validate_nvs(nvs, skip_check = False):
    ok = True
    if not validate_url(nvs['WAS']['URL'], True):
        ok = False
    if not validate_wifi_psk(nvs['WIFI']['PSK']):
        ok = False
    if not validate_wifi_ssid(nvs['WIFI']['SSID']):
        ok = False
    if not skip_check:
        if not test_url(nvs['WAS']['URL'],
                        f":red[Unable to open WebSocket connection to WAS URL on {nvs['WAS']['URL']}]", True):
            ok = False
    return ok


def validate_string(string, error_msg, min_len=1):
    if len(string) < min_len:
        #st.write(f":red[{error_msg}]")
        return False
    return True


def validate_url(url, ws=False):
    if ws:
        pattern = "^wss?://"
    else:
        pattern = "^https?://"

    if re.match(pattern, url):
        return True
    #st.write(f":red[Invalid URL: {url}]")
    return False


def validate_wifi_psk(psk):
    if len(psk) < 8 or len(psk) > 63:
        #st.write(":red[Wi-Fi WPA passphrase must be between 8 and 63 ASCII characters]")
        return False
    return True


def validate_wifi_ssid(ssid):
    # TODO:detect non-ASCII characters (fastapi converts them to \u.... \
    # the re.match we used in CMake doesn't catch those
    if len(ssid) < 2 or len(ssid) > 32:
        #st.write(":red[Wi-Fi SSID must be between 2 and 32 ASCII characters]")
        return False
    return True


def warm_tts(data):
    try:
        if "/api/tts" in data["audio_url"]:
            do_get_request(data["audio_url"])
            log.debug("TTS ready - passing to clients")
    except:
        pass
