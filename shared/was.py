import json
import requests


URL_WAS_API_CLIENTS = 'http://localhost:8502/api/clients'
URL_WAS_API_OTA = 'http://localhost:8502/api/ota'

URL_WAS_API_CONFIG = "http://localhost:8502/api/config"
URL_WAS_API_CONFIG_APPLY = "http://localhost:8502/api/config/apply"
URL_WAS_API_CONFIG_SAVE = "http://localhost:8502/api/config/save"
URL_WAS_API_NVS = "http://localhost:8502/api/nvs"

def apply_config():
    requests.post(f"{URL_WAS_API_CONFIG_APPLY}")

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

def get_config():
	response = requests.get(URL_WAS_API_CONFIG)
	json = response.json()
	return json

def get_devices():
    response = requests.get(URL_WAS_API_CLIENTS)
    json = response.json()
    return json

def get_ha_entities(url, token):
    if token is None:
        return json.dumps({'error':'HA token not set'})

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    url = f"{url}/api/states"
    response = requests.get(url, headers=headers)
    json = response.json()
    json.sort(key=lambda x: x['entity_id'])
    return json

def get_nvs():
	response = requests.get(URL_WAS_API_NVS)
	json = response.json()
	return json

def get_tz():
    try:
        with open("tz.json", "r") as config_file:
            tz = json.load(config_file)
        config_file.close()
    except:
        tz = {}

    return tz

def merge_dict(dict_1, dict_2):
	result = dict_1 | dict_2
	return result

def num_devices():
    return(len(get_devices()))

def ota(hostname):
    requests.post(URL_WAS_API_OTA, json={'hostname': hostname})

def post_config(json, apply=False):
    if apply:
        url = URL_WAS_API_CONFIG_APPLY
    else:
        url = URL_WAS_API_CONFIG_SAVE
    requests.post(url, json = json)

def post_nvs(json):
	requests.post(URL_WAS_API_NVS, json=json)
