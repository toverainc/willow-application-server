import json
import os
import sys

STORAGE_USER_CLIENT_CONFIG = '/app/storage/user_client_config.json'
STORAGE_DEVICES_CONFIG = '/app/storage/devices.json'

def hex_mac(mac):
    if type(mac) == list:
        mac = '%02x:%02x:%02x:%02x:%02x:%02x' % (mac[0], mac[1], mac[2], mac[3], mac[4], mac[5])
    return mac

def save_json_to_file(path, content):
    with open(path, "w") as config_file:
        config_file.write(content)
    config_file.close()

if os.path.isfile(STORAGE_USER_CLIENT_CONFIG):
    sys.exit()

if os.path.isfile(STORAGE_DEVICES_CONFIG):
    print('Migrating legacy WAS client configuration...')
    devices_file = open(STORAGE_DEVICES_CONFIG, "r")
    devices = json.load(devices_file)
    devices_file.close()

    new_devices=[]
    for device in devices:
        mac_addr = hex_mac(device["mac_addr"])
        label = device["label"]
        user_config = {"mac_addr": mac_addr, "label": label}
        new_devices.append(user_config)

    save_json_to_file(STORAGE_USER_CLIENT_CONFIG, json.dumps(new_devices))