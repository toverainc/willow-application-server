import json
import pandas as pd
import streamlit as st

from shared.was import get_devices


title = "Willow Application Server - Devices"

st.set_page_config(page_title=title, layout = 'centered', initial_sidebar_state = 'auto')
st.title(title)

devices = get_devices()
df = pd.read_json(json.dumps(devices))

st.table(df)
