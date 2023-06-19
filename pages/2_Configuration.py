import streamlit as st
import json
import requests

was_api_config = "http://api:8502/api/config"

def post_config(json):
    requests.post(was_api_config, json = json)

def get_config():
    response = requests.get(was_api_config)
    json = response.json()
    return json

def merge_dict(dict_1, dict_2):
	result = dict_1 | dict_2
	return result

title = "Willow Application Server - Configuration"

st.set_page_config(page_title=title, layout = 'centered', initial_sidebar_state = 'auto')
st.title(title)

try:
    user_config = get_config()
except:
    user_config = {}

try:
    with open("default_config.json", "r") as config_file:
        default_config = json.load(config_file)
except:
    default_config = {}

config = merge_dict(default_config, user_config)

config["wifi_ssid"] = st.text_input("WiFi SSID", value=config["wifi_ssid"])
config["wifi_password"] = st.text_input("WiFi Password", value=config["wifi_password"])

speech_rec_mode_values = ('WIS', 'Multinet')
config["speech_rec_mode"] = st.selectbox(
    "Willow Speech Recognition Mode",
    speech_rec_mode_values, speech_rec_mode_values.index(config["speech_rec_mode"]))

if config["speech_rec_mode"] == "WIS":
    config["wis_url"] = st.text_input("Willow Inference Server URL", value=config["wis_url"])

audio_response_type_values = ('None', 'Chimes', 'TTS')
config["audio_response_type"] = st.selectbox(
    "Willow audio response type",
    audio_response_type_values, audio_response_type_values.index(config["audio_response_type"]))

if config["audio_response_type"] == "TTS":
    config["wis_tts_url"] = st.text_input("Willow Inference Server TTS URL", value=config["wis_tts_url"])

wake_word_values = ('Hi ESP', 'Alexa', 'Hi Lexin')
config["wake_word"] = st.selectbox(
    "Willow Wake Word",
    wake_word_values, wake_word_values.index(config["wake_word"]))

command_endpoint_values = ('Home Assistant', 'openHAB', 'REST')
config["command_endpoint"] = st.selectbox(
    "Willow Command Endpoint",
    command_endpoint_values, command_endpoint_values.index(config["command_endpoint"]))

if config["command_endpoint"] == "Home Assistant":
    config["hass_host"] = st.text_input("Home Assistant Host", value=config["hass_host"])
    config["hass_port"] = st.number_input("Home Assistant Port", min_value=1, max_value=65535, value=config["hass_port"])
    config["hass_tls"] = st.checkbox('Home Assistant use TLS', value=config["hass_tls"])
    config["hass_token"] = st.text_input("Home Assistant Token", value=config["hass_token"])

if config["command_endpoint"] == "openHAB":
    config["openhab_url"] = st.text_input("openHAB URL", value=config["openhab_url"])
    config["openhab_token"] = st.text_input("openHAB Token", value=config["openhab_token"])

if config["command_endpoint"] == "REST":
    config["rest_url"] = st.text_input("REST URL", value=config["rest_url"])

    rest_auth_type_values = ('None', 'Basic', 'Header')
    config["rest_auth_type"] = st.selectbox(
    "REST Authentication Method",
    rest_auth_type_values, rest_auth_type_values.index(config["rest_auth_type"]))

    if config["rest_auth_type"] == "Basic":
        config["rest_auth_user"] = st.text_input("REST Basic Username", value=config["rest_auth_user"])
        config["rest_auth_pass"] = st.text_input("REST Basic Password", value=config["rest_auth_pass"])
    elif config["rest_auth_type"] == "Header":
        config["rest_auth_header"] = st.text_input("REST Authentication Header", value=config["rest_auth_header"])

config["timezone"] = st.text_input("Timezone",value=config["timezone"])

config["speaker_volume"] = st.slider('Speaker Volume', 0, 100, value=config["speaker_volume"])

config["lcd_brightness"] = st.slider('LCD Brightness', 0, 1023, value=config["lcd_brightness"])

ntp_config_values = ('Host', 'DHCP')
config["ntp_config"] = st.selectbox(
    "NTP Configuration",
    ntp_config_values, ntp_config_values.index(config["ntp_config"]))

if config["ntp_config"] == "Host":
    config["ntp_host"] = st.text_input("NTP Host",value=config["ntp_host"])

# Form submit button
submitted = st.button("Save and Apply")
if submitted:
    json_object = json.dumps(config, indent=2)
    post_config(json_object)
    st.write(f"Configuration Saved:")
    st.json(config)
