import streamlit as st
import json

title = "Willow Application Server"

st.set_page_config(page_title=title, layout = 'centered', initial_sidebar_state = 'auto')
st.title(title)

try: 
    with open("user_config.json", "r") as config_file:
        config = json.load(config_file)
except:
    with open("default_config.json", "r") as config_file:
        config = json.load(config_file)

config["wifi_ssid"] = st.text_input("WiFi SSID", value=config["wifi_ssid"])
config["wifi_password"] = st.text_input("WiFi Password", value=config["wifi_password"])

config["speech_rec_mode"] = st.selectbox(
    "Willow Speech Recognition Mode",
    ('WIS', 'Multinet'))

if config["speech_rec_mode"] == "WIS":
    config["wis_url"] = st.text_input("Willow Inference Server URL", value=config["wis_url"])

config["response_type"] = st.selectbox(
    "Willow audio response type",
    ('None', 'Chimes', 'TTS'))

if config["response_type"] == "TTS":
    config["wis_tts_url"] = st.text_input("Willow Inference Server TTS URL", value=config["wis_tts_url"])

config["wake_word"] = st.selectbox(
    "Willow Wake Word",
    ('Hi ESP', 'Alexa', 'Hi Lexin'))

config["command_endpoint"] = st.selectbox(
    "Willow Command Endpoint",
    ('Home Assistant', 'openHAB', 'REST'))

if config["command_endpoint"] == "Home Assistant":
    config["hass_host"] = st.text_input("Home Assistant Host", value=config["hass_host"])
    config["hass_port"] = st.number_input("Home Assistant Port", min_value=1, max_value=65535, value=config["hass_port"])
    config["hass_tls"] = st.checkbox('Home Assistant use TLS', value=config["hass_tls"])
    config["hass_token"] = st.text_input("Home Assistant Token", value=config["hass_token"])

config["timezone"] = st.text_input("Timezone",value=config["timezone"])

config["speaker_volume"] = st.slider('Speaker Volume', 0, 100, value=config["speaker_volume"])

config["lcd_brightness"] = st.slider('LCD Brightness', 0, 1023, value=config["lcd_brightness"])

config["ntp_config"] = st.selectbox(
    "NTP Configuration",
    ('Host', 'DHCP'))

if config["ntp_config"] == "Host":
    config["ntp_host"] = st.text_input("NTP Host",value=config["ntp_host"])

# Form submit button
submitted = st.button("Save")
if submitted:
    json_object = json.dumps(config, indent=2)
    with open("user_config.json", "w") as config_file:
        config_file.write(json_object)
    st.write(f"Configuration Saved:")
    st.json(config)