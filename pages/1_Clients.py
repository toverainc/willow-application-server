import json
import pandas as pd
import requests
import streamlit as st

from shared.was import get_devices, ota


title = "Willow Application Server - Devices"

st.set_page_config(page_title=title, layout = 'centered', initial_sidebar_state = 'auto')
st.title(title)

devices = get_devices()
cols = st.columns(5)
fields = ["Hostname", "IP", "Port", "User Agent", "Actions"]

for col, field in zip(cols, fields):
    col.write(f"**{field}**")


for idx, row in enumerate(devices):
    hostname, ip, port, user_agent, actions = st.columns(5)
    hostname.write(row['hostname'])
    ip.write(row['ip'])
    port.write(row['port'])
    user_agent.write(row['user_agent'])
    actions.button(key=idx, kwargs=dict(hostname=row['hostname']), label="OTA", on_click=ota, type="primary")
