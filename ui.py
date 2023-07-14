import json
import streamlit as st

from copy import deepcopy
from os import environ
from shared.was import (
    STORAGE_USER_MULTINET,
    apply_config_host,
    apply_nvs_host,
    construct_url,
    delete_release,
    get_ip,
    get_nvs,
    ota,
    get_clients,
    get_config,
    get_ha_commands_for_entity,
    get_ha_entities,
    get_release_gh_latest,
    get_releases,
    get_tz,
    merge_dict,
    num_clients,
    post_config,
    post_nvs,
    validate_config,
    validate_nvs,
)


try:
    user_config = get_config()
except Exception:
    user_config = {}

try:
    user_nvs = get_nvs()
except Exception:
    user_nvs = {}

try:
    with open("default_config.json", "r") as config_file:
        default_config = json.load(config_file)
    config_file.close()
except Exception:
    default_config = {}

try:
    with open("default_nvs.json", "r") as nvs_file:
        default_nvs = json.load(nvs_file)
    nvs_file.close()
except Exception:
    default_nvs = {}

connected_clients = get_clients()
latest_release = get_release_gh_latest()
outdated_clients = 0
releases = {}
if len(user_nvs) != 0:
    releases = get_releases(user_nvs["WAS"]["URL"])

# latest_release is None when we hit Github rate-limit
if latest_release is not None:
    for client in connected_clients:
        willow_version = client['user_agent'].replace('Willow/', '')
        if willow_version != latest_release:
            outdated_clients += 1

title = 'Willow Application Server'

st.set_page_config(page_title=title, layout='wide')
st.title(title)

if len(user_config) == 0 or len(user_nvs) == 0:
    st.info("Welcome to the Willow Application Server. Go to the configuration tab to get started.")

home, clients, configuration, multinet, updates = st.tabs(["Home", "Clients", "Configuration", "Multinet", "Updates"])

with home:
    col1, col2 = st.columns(2)
    with col1:
        st.metric(label='Connected Clients', value=num_clients())
    with col2:
        st.metric(label='Outdated Clients', value=outdated_clients)

with clients:
    cols = st.columns(5)
    fields = ["Hostname", "Hardware Type", "Remote", "Version", "Actions"]

    for col, field in zip(cols, fields):
        col.write(f"**{field}**")

    for idx, row in enumerate(connected_clients):
        if row['hostname'] == "unknown" or row['hw_type'] == "unknown":
            continue
        hostname, hw_type, remote, version, actions = st.columns(5)
        hostname.write(row['hostname'])
        hw_type.write(row['hw_type'])
        remote.write(f"{row['ip']}:{row['port']}")
        willow_version = row['user_agent'].replace('Willow/', '')
        version.write(willow_version)
        actions.button(key=f"btn_apply_cfg_{idx}", kwargs=dict(hostname=row['hostname']), label="Apply Config",
                       on_click=apply_config_host, type="primary")
        actions.button(key=f"btn_apply_nvs_{idx}", kwargs=dict(hostname=row['hostname']), label="Apply NVS",
                       on_click=apply_nvs_host, type="primary")

        if len(releases) > 0:
            # if there's a local OTA file for at least one hw type but not all hw types, we can hit a KeyError
            device_releases = deepcopy(releases)
            for release in list(device_releases):
                if releases[release].get(row['hw_type']) is None:
                    device_releases.pop(release)

            version.selectbox("Select release to flash", device_releases, key=f"sb_ota_{idx}")
            version.button(key=f"btn_ota_{idx}", kwargs=dict(hostname=row['hostname'],
                           info=releases[st.session_state[f"sb_ota_{idx}"]][row['hw_type']],
                           version=st.session_state[f"sb_ota_{idx}"]), label="OTA", on_click=ota, type="primary")

with configuration:
    was_url = ""
    if len(user_nvs) == 0:
        try:
            if environ.get('WAS_IP') is not None:
                was_url = f"ws://{environ['WAS_IP']}:8502/ws"
            else:
                was_url = f"ws://{get_ip()}:8502/ws"
            st.info("We tried to guess your WAS URL. Please make sure your Willow devices can reach this URL!")
        except Exception:
            st.info("We couldn't guess your WAS URL. Please make sure your Willow devices can reach the URL you enter!")
    else:
        was_url = user_nvs["WAS"]["URL"]

    if len(user_config) > 0 and len(user_nvs) > 0:
        st.info(f"Ready to flash. Go to "
                f"[https://flash.heywillow.io](https://flash.heywillow.io?wasURL={was_url})")

    config = merge_dict(default_config, user_config)
    nvs = merge_dict(default_nvs, user_nvs)

    expander_connectivity = st.expander(label='Connectivity')
    with expander_connectivity:

        nvs["WAS"]["URL"] = st.text_input("Willow Application Server URL", value=was_url)
        nvs["WIFI"]["SSID"] = st.text_input("WiFi SSID", value=nvs["WIFI"]["SSID"])
        nvs["WIFI"]["PSK"] = st.text_input("WiFi Password", value=nvs["WIFI"]["PSK"])

        skip_connectivity_checks_nvs = st.checkbox(key='skip_connectivity_checks_nvs', label='Skip connectivity checks')

        # NVS form submit button
        nvs_apply = st.button("Save and Apply", key="btn_nvs")
        if nvs_apply:
            if validate_nvs(nvs):
                json_object = json.dumps(nvs, indent=2)
                post_nvs(json_object, True)
                st.write("NVS values saved")
                st.json(nvs)
                st.experimental_rerun()

        nvs_save = st.button("Save", key="btn_nvs_save")
        if nvs_save:
            if validate_nvs(nvs):
                json_object = json.dumps(nvs, indent=2)
                post_nvs(json_object, False)
                st.write("NVS values saved")
                st.json(nvs)
                st.experimental_rerun()

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

        wake_words = {'hiesp': 'Hi ESP', 'alexa': 'Alexa', 'hilexin': 'Hi Lexin'}
        config["wake_word"] = st.selectbox(
            "Willow Wake Word",
            wake_words, index=list(wake_words.keys()).index(config["wake_word"]),
            format_func=lambda x: wake_words.get(x))

        command_endpoint_values = ('Home Assistant', 'openHAB', 'REST')
        config["command_endpoint"] = st.selectbox(
            "Willow Command Endpoint",
            command_endpoint_values, command_endpoint_values.index(config["command_endpoint"]))

        if config["command_endpoint"] == "Home Assistant":
            config["hass_host"] = st.text_input("Home Assistant Host", value=config["hass_host"])
            config["hass_port"] = st.number_input("Home Assistant Port", min_value=1, max_value=65535,
                                                  value=config["hass_port"])
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
                config["rest_auth_header"] = st.text_input("REST Authentication Header",
                                                           value=config["rest_auth_header"])

        tzdata = get_tz()
        tzkeys = list(tzdata.keys())
        tzvalues = list(tzdata.values())
        tzidx = tzkeys.index(config["timezone_continent_city"])
        tz = st.selectbox(label="Timezone", options=tzdata.keys(), index=tzidx)
        config["timezone"] = tzdata[tz]
        config["timezone_continent_city"] = tz

        config["speaker_volume"] = st.slider('Speaker Volume', 0, 100, value=config["speaker_volume"])

        config["lcd_brightness"] = st.slider('LCD Brightness', 0, 1023, value=config["lcd_brightness"])

        ntp_config_values = ('Host', 'DHCP')
        config["ntp_config"] = st.selectbox(
            "NTP Configuration",
            ntp_config_values, ntp_config_values.index(config["ntp_config"]))

        if config["ntp_config"] == "Host":
            config["ntp_host"] = st.text_input("NTP Host", value=config["ntp_host"])

        advanced = st.checkbox(label='Show advanced settings')
        if advanced:
            config["aec"] = st.checkbox(key="aec", label="Acoustic Echo Cancellation", value=config["aec"])
            config["bss"] = st.checkbox(key="bss", label="Blind Source Separation", value=config["bss"])

            audio_codecs = ('AMR-WB', 'PCM', 'WAV')
            config["audio_codec"] = st.selectbox("Audio codec to use for streaming to WIS",
                                                 audio_codecs, audio_codecs.index(config["audio_codec"]))

            vad_help = "Higher modes are more aggressive and are more restrictive in detecting speech"
            vad_modes = (0, 1, 2, 3, 4)
            config["vad_mode"] = st.selectbox("Voice Activity Detection Mode", vad_modes,
                                              vad_modes.index(config["vad_mode"]), help=vad_help)
            wake_help = '''The probability of being recognized as a wake word increases with increasing mode.
                        As a consequence, a higher mode will result in more false positives.'''
            wake_modes = ('1CH_90', '1CH_95', '2CH_90', '2CH_95', '3CH_90', '3CH_95')
            config["wake_mode"] = st.selectbox("Wake Word Recognition Mode", wake_modes,
                                               wake_modes.index(config["wake_mode"]), help=wake_help)

            mic_gain_help = '''0dB (0), 3dB (1), 6dB (2), 9dB (3), 12dB (4), 15dB (5), 18dB (6), 21dB (7),
                          24dB (8), 27dB (9), 30dB (10), 33dB (11), 34.5dB (12), 36dB (13), 37.5 (dB)'''
            config["mic_gain"] = st.slider("Microphone Gain", 0, 14, value=config["mic_gain"], help=mic_gain_help)

            record_buffer_help = '''Custom record buffer for timing and latency.
                                 Users with a local WIS instance may want to try setting lower (10 or so)'''
            config["record_buffer"] = st.slider("Record Buffer", 1, 16, value=config["record_buffer"],
                                                help=record_buffer_help)

            stream_timeout_help = '''Stop speech recognition after N seconds after wake event
                                  to avoid endless stream when VAD END does not trigger.'''
            config["stream_timeout"] = st.slider("Maximum speech duration", 1, 30, value=config["stream_timeout"],
                                                 help=stream_timeout_help)

            vad_timeout_help = '''VAD (Voice Activity Detection) timeout in ms.
                               How long to wait after end of speech to trigger end of VAD.
                               Improves response times but can also clip speech if you do not talk fast enough.
                               Allows for entering 1 - 1000 ms but if you go lower than 50 or so good luck...'''
            config["vad_timeout"] = st.slider("VAD Timeout", 1, 1000, value=config["vad_timeout"],
                                              help=vad_timeout_help)

        skip_connectivity_checks = st.checkbox(key='skip_connectivity_checks', label='Skip connectivity checks')

        # Config form submit button
        config_save = st.button("Save")
        if config_save:
            if validate_config(config):
                json_object = json.dumps(config, indent=2)
                post_config(json_object, False)
                st.write("Configuration Saved:")
                st.json(config)
                st.experimental_rerun()

        config_apply = st.button("Save and Apply")
        if config_apply:
            if validate_config(config):
                json_object = json.dumps(config, indent=2)
                post_config(json_object, True)
                st.write("Configuration Saved:")
                st.json(config)
                st.experimental_rerun()

with multinet:
    if config["speech_rec_mode"] != "Multinet":
        st.warning("Speech Recognition Mode is not set to Multinet.")
    else:
        st.warning("""
            We currently do not support dynamic Multinet model generation.
            If you want to use Multinet you need to build using the willow-build container.
        """)

        if config["command_endpoint"] == "Home Assistant":
            entity_types = ["cover", "fan", "light", "scene", "switch"]
            cols = st.columns(len(entity_types))

            for col, field in zip(cols, entity_types):
                with col:
                    st.checkbox(field, key=f"{field}")

            ha_commands = []
            fetch_ha = st.button("Generate Multinet commands for selected Home Assistant entity types")
            save_ha = st.button("Save commands")

            if fetch_ha:
                ha_url = construct_url(config["hass_host"], config["hass_port"], config["hass_tls"])
                ha_entities = get_ha_entities(ha_url, config["hass_token"])

                for entity in ha_entities:
                    if 'friendly_name' in entity['attributes']:
                        entity_type = entity['entity_id'].split('.')[0]
                        if entity_type in st.session_state and st.session_state[entity_type]:
                            friendly_name = entity['attributes']['friendly_name']
                            ha_commands.extend(get_ha_commands_for_entity(friendly_name))

            else:
                if not save_ha:
                    try:
                        multinet_commands_file = open(STORAGE_USER_MULTINET, "r")
                        ha_commands = json.load(multinet_commands_file)
                    except Exception:
                        pass

                if len(ha_commands) == 0 and 'ha_commands' in st.session_state:
                    ha_commands = st.session_state["ha_commands"]

            ha_commands = st.data_editor(data=ha_commands, num_rows="dynamic", use_container_width=True)
            st.session_state["ha_commands"] = ha_commands

            if save_ha:
                with open(STORAGE_USER_MULTINET, "w") as multinet_commands:
                    multinet_commands.write(json.dumps(st.session_state["ha_commands"]))
                multinet_commands.close()

                st.session_state["ha_commands"] = ha_commands

with updates:
    # we need the WAS URL to refresh releases so hide button and warning when there is no user NVS config
    if len(user_nvs) != 0:
        if latest_release is None or len(releases) == 0:
            st.warning("Unable to get Github releases. Might be caused by Github rate limits.")

        btn_refresh = st.button(label="Refresh releases", help="Refresh Github and local releases")
        if btn_refresh:
            releases = get_releases(user_nvs["WAS"]["URL"], refresh=True)

    for release in releases.keys():
        if release == latest_release:
            st.header(f"{release} (latest)")
        else:
            st.header(release)

        cols = st.columns(3)
        fields = ["Hardware Type", "Cached", "Delete"]

        for col, field in zip(cols, fields):
            col.write(f"**{field}**")
        for device in releases[release].keys():
            hw_type, cached, delete = st.columns(3)
            hw_type.write(device)
            if release == 'local':
                cached.write('local')
            else:
                cached.write(releases[release][device]['cached'])

            with delete:
                btn_key = f"btn_delete_{release}_{device}"
                st.button(key=btn_key, label="Delete", disabled=not releases[release][device]['cached'],
                          kwargs=dict(releases[release][device], release=release), on_click=delete_release)

        st.divider()
