import json
import re
import requests
import socket

from num2words import num2words
from websockets.sync.client import connect


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


def merge_dict(dict_1, dict_2):
    result = dict_1 | dict_2
    return result


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
