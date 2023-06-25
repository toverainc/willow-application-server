import json
import pandas as pd
import requests
import streamlit as st

from shared.was import *


title = 'Willow Application Server'

st.set_page_config(page_title=title, layout='wide')
st.title(title)

home, clients, configuration, multinet = st.tabs(["Home", "Clients", "Configuration", "Multinet"])

with home:
    st.metric(label='Connected Clients', value=num_devices())


with clients:
	devices = get_devices()
	cols = st.columns(6)
	fields = ["Hostname", "Hardware Type", "IP", "Port", "User Agent", "Actions"]

	for col, field in zip(cols, fields):
		col.write(f"**{field}**")


	for idx, row in enumerate(devices):
		if row['hostname'] == "unknown" or row['hw_type'] == "unknown":
			continue
		hostname, hw_type, ip, port, user_agent, actions = st.columns(6)
		hostname.write(row['hostname'])
		hw_type.write(row['hw_type'])
		ip.write(row['ip'])
		port.write(row['port'])
		user_agent.write(row['user_agent'])
		actions.button(key=idx, kwargs=dict(hostname=row['hostname']), label="OTA", on_click=ota, type="primary")


with configuration:

    try:
        user_config = get_config()
    except:
        user_config = {}

    try:
        user_nvs = get_nvs()
    except:
        user_nvs = {}

    try:
        with open("default_config.json", "r") as config_file:
            default_config = json.load(config_file)
        config_file.close()
    except:
        default_config = {}

    try:
        with open("default_nvs.json", "r") as nvs_file:
            default_nvs = json.load(nvs_file)
        nvs_file.close()
    except:
        default_nvs = {}

    config = merge_dict(default_config, user_config)
    nvs = merge_dict(default_nvs, user_nvs)


    expander_connectivity = st.expander(label='Connectivity')
    with expander_connectivity:

        nvs["WAS"]["URL"] = st.text_input("Willow Application Server URL", value=nvs["WAS"]["URL"])
        nvs["WIFI"]["SSID"] = st.text_input("WiFi SSID", value=nvs["WIFI"]["SSID"])
        nvs["WIFI"]["PSK"] = st.text_input("WiFi Password", value=nvs["WIFI"]["PSK"])

        # NVS form submit button
        nvs_submitted = st.button("Save and Apply", key="btn_nvs")
        if nvs_submitted:
            json_object = json.dumps(nvs, indent=2)
            post_nvs(json_object)
            st.write("NVS values saved")
            st.json(nvs)


    expander_main = st.expander(label='Main settings')
    with expander_main:

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


        advanced = st.checkbox(label='Show advanced settings')
        if advanced:

            audio_codecs = ('AMR-WB', 'PCM', 'WAV')
            config["audio_codec"] = st.selectbox("Audio codec to use for streaming to WIS",
                    audio_codecs, audio_codecs.index(config["audio_codec"])
            )

            vad_modes = (0, 1, 2, 3, 4)
            config["vad_mode"] = st.selectbox("Voice Activity Detection Mode",
                    vad_modes, vad_modes.index(config["vad_mode"]),
                    help='''Higher modes are more aggressive and are more restrictive in detecting speech'''
            )

            wake_modes = ('1CH_90', '1CH_95', '2CH_90', '2CH_95', '3CH_90', '3CH_95')
            config["wake_mode"] = st.selectbox("Wake Word Recognition Mode",
                    wake_modes, wake_modes.index(config["wake_mode"]),
                    help='''The probability of being recognized as a wake word increases with increasing mode.
                    As a consequence, a higher mode will result in more false positives.'''
            )

            config["mic_gain"] = st.slider("Microphone Gain", 0, 14, value=config["mic_gain"],
                    help='''0dB (0), 3dB (1), 6dB (2), 9dB (3), 12dB (4), 15dB (5), 18dB (6), 21dB (7),
                    24dB (8), 27dB (9), 30dB (10), 33dB (11), 34.5dB (12), 36dB (13), 37.5 (dB)'''
            )

            config["record_buffer"] = st.slider("Record Buffer", 1, 16, value=config["record_buffer"],
                    help='''Custom record buffer for timing and latency.
                    Users with a local WIS instance may want to try setting lower (10 or so)'''
            )

            config["stream_timeout"] = st.slider("Maximum speech duration", 1, 30, value=config["stream_timeout"],
                    help='Stop speech recognition after N seconds after wake event to avoid endless stream when VAD END does not trigger.'
            )

            config["vad_timeout"] = st.slider("VAD Timeout", 1, 1000, value=config["vad_timeout"],
                    help='''VAD (Voice Activity Detection) timeout in ms - How long to wait after end of speech to trigger end of VAD.
                    Improves response times but can also clip speech if you do not talk fast enough.
                    Allows for entering 1 - 1000 ms but if you go lower than 50 or so good luck...'''
            )

        # Config form submit button
        config_submitted = st.button("Save and Apply")
        if config_submitted:
            json_object = json.dumps(config, indent=2)
            post_config(json_object)
            st.write(f"Configuration Saved:")
            st.json(config)

with multinet:
    if config["speech_rec_mode"] != "Multinet":
        st.warning("Speech Recognition Mode is not set to Multinet.")
    else:
        st.warning("""
            We currently do not support dynamic Multinet model generation.
            If you want to use Multinet you need to build using the willow-build container.
        """)
