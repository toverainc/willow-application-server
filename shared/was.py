import json
import requests


URL_WAS_API_CLIENTS = 'http://api:8502/api/clients'


def get_devices():
    response = requests.get(URL_WAS_API_CLIENTS)
    json = response.json()
    return json
