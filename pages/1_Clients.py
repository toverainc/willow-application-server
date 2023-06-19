import streamlit as st

from shared.was import get_devices


title = "Willow Application Server - Devices"

st.set_page_config(page_title=title, layout = 'centered', initial_sidebar_state = 'auto')
st.title(title)


devices = get_devices()
for device in devices:
    st.write(device)
