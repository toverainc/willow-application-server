import streamlit as st

from shared.was import num_devices


title = 'Willow Application Server'

st.set_page_config(page_title=title, layout='wide')

st.title(title)

st.metric(label='Connected Clients', value=num_devices())
