import json
import requests


URL_WAS_API_CLIENTS = 'http://localhost:8502/api/clients'
URL_WAS_API_OTA = 'http://localhost:8502/api/ota'


def get_devices():
    response = requests.get(URL_WAS_API_CLIENTS)
    json = response.json()
    return json

def ota(hostname):
    requests.post(URL_WAS_API_OTA, json={'hostname': hostname})
