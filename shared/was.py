import json
import os
import re
import requests
import socket

from num2words import num2words
from websockets.sync.client import connect

DIR_OTA = 'storage/ota'
URL_WILLOW_RELEASES = 'https://worker.heywillow.io/releases?format=was'
URL_GH_RELEASES_LATEST = 'https://worker.heywillow.io/releases/latest'

STORAGE_DEVICES = 'storage/devices.json'
STORAGE_USER_CONFIG = 'storage/user_config.json'
STORAGE_USER_MULTINET = 'storage/user_multinet.json'
STORAGE_USER_NVS = 'storage/user_nvs.json'

URL_WAS_API_CLIENTS = 'http://localhost:8502/api/clients'
URL_WAS_API_DEVICE = 'http://localhost:8502/api/device'
URL_WAS_API_DEVICES = 'http://localhost:8502/api/devices'
URL_WAS_API_DEVICE_RESTART = 'http://localhost:8502/api/device/restart'
URL_WAS_API_OTA = 'http://localhost:8502/api/ota'
URL_WAS_API_RELEASES_GITHUB = 'http://localhost:8502/api/releases/github'
URL_WAS_API_RELEASES_INTERNAL = 'http://localhost:8502/api/releases/internal'
URL_WAS_API_RELEASE_CACHE = 'http://localhost:8502/api/release/cache'
URL_WAS_API_RELEASE_DELETE = 'http://localhost:8502/api/release/delete'

URL_WAS_API_CONFIG = "http://localhost:8502/api/config"
URL_WAS_API_CONFIG_APPLY = "http://localhost:8502/api/config/apply"
URL_WAS_API_CONFIG_SAVE = "http://localhost:8502/api/config/save"
URL_WAS_API_NVS = "http://localhost:8502/api/nvs"
URL_WAS_API_NVS_APPLY = "http://localhost:8502/api/nvs/apply"
URL_WAS_API_NVS_SAVE = "http://localhost:8502/api/nvs/save"


def apply_config():
    requests.post(f"{URL_WAS_API_CONFIG_APPLY}")


def apply_config_host(hostname):
    requests.post(URL_WAS_API_CONFIG_APPLY, json={'hostname': hostname})


def apply_nvs_host(hostname):
    requests.post(URL_WAS_API_NVS_APPLY, json={'hostname': hostname})


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


def delete_release(**kwargs):
    data = {}
    data['path'] = f"{DIR_OTA}/{kwargs['release']}/{kwargs['file_name']}"

    requests.post(URL_WAS_API_RELEASE_DELETE, json=data)


def get_clients():
    response = requests.get(URL_WAS_API_CLIENTS)
    json = response.json()
    return json


def get_config():
    response = requests.get(URL_WAS_API_CONFIG)
    json = response.json()
    return json


def get_device_label(mac_addr):
    devices = get_devices()
    for device in devices:
        if device['mac_addr'] == mac_addr:
            if 'label' in device:
                return device['label']


def get_devices():
    response = requests.get(URL_WAS_API_DEVICES)
    return response.json()


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


def get_nvs():
    response = requests.get(URL_WAS_API_NVS)
    json = response.json()
    return json


def get_release_willow_latest():
    response = requests.get(URL_WILLOW_RELEASES)
    json = response.json()
    if json.get('latest'):
        return json['tag_name']
    else:
        return None


def get_releases_willow():
    releases = requests.get(URL_WILLOW_RELEASES)
    return releases.json()


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


def merge_dict(dict_1, dict_2):
    result = dict_1 | dict_2
    return result


def num_clients():
    return (len(get_clients()))


def ota(hostname, info, version):
    info['version'] = version
    if version != 'local':
        requests.post(URL_WAS_API_RELEASE_CACHE, json=info)
    requests.post(URL_WAS_API_OTA, json={'hostname': hostname, 'ota_url': info['was_url']})


def post_config(json, apply=False):
    if apply:
        url = URL_WAS_API_CONFIG_APPLY
    else:
        url = URL_WAS_API_CONFIG_SAVE
    requests.post(url, json=json)


def post_device(data):
    requests.post(URL_WAS_API_DEVICE, json=data)


def post_nvs(json, apply=False):
    if apply:
        url = URL_WAS_API_NVS_APPLY
    else:
        url = URL_WAS_API_NVS_SAVE
    requests.post(url, json=json)


def restart_device(hostname):
    requests.post(URL_WAS_API_DEVICE_RESTART, json={'hostname': hostname})


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
    # TODO:detect non-ASCII characters (streamlit or fastapi converts them to \u.... \
    # the re.match we used in CMake doesn't catch those
    if len(ssid) < 2 or len(ssid) > 32:
        #st.write(":red[Wi-Fi SSID must be between 2 and 32 ASCII characters]")
        return False
    return True
