from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict


class WillowAudioCodec(str, Enum):
    AMR_WB = 'AMR-WB'
    PCM = 'PCM'


class WillowAudioResponseType(str, Enum):
    Chimes = 'Chimes'
    none = 'None'
    TTS = 'TTS'


class WillowCommandEndpoint(str, Enum):
    HomeAssistant = 'Home Assistant'
    openHAB = 'openHAB'
    MQTT = 'MQTT'
    REST = 'REST'


class WillowMqttAuthType(str, Enum):
    none = 'none'
    userpw = 'userpw'


class WillowNtpConfig(str, Enum):
    Host = 'Host'
    DHCP = 'DHCP'


class WillowRestAuthType(str, Enum):
    none = 'None'
    Basic = 'Basic'
    Header = 'Header'


class WillowSpeechRecMode(str, Enum):
    WIS = 'WIS'


class WillowWakeMode(str, Enum):
    _1CH_90 = '1CH_90'
    _1CH_95 = '1CH_95'
    _2CH_90 = '2CH_90'
    _2CH_95 = '2CH_95'
    _3CH_90 = '3CH_90'
    _3CH_95 = '3CH_95'


class WillowWakeWord(str, Enum):
    alexa = 'alexa'
    hiesp = 'hiesp'
    hilexin = 'hilexin'


class WillowConfig(BaseModel, validate_assignment=True):
    aec: bool = None
    audio_codec: WillowAudioCodec = None
    audio_response_type: WillowAudioResponseType = None
    bss: bool = None
    command_endpoint: WillowCommandEndpoint = None
    display_timeout: int = None
    hass_host: Optional[str] = None
    hass_port: Optional[int] = None
    hass_tls: Optional[bool] = None
    hass_token: Optional[str] = None
    lcd_brightness: int = None
    mic_gain: int = None
    mqtt_auth_type: Optional[WillowMqttAuthType] = None
    mqtt_host: Optional[str] = None
    mqtt_password: Optional[str] = None
    mqtt_port: Optional[int] = None
    mqtt_tls: Optional[bool] = None
    mqtt_topic: Optional[str] = None
    mqtt_username: Optional[str] = None
    multiwake: bool = None
    ntp_config: WillowNtpConfig = None
    ntp_host: Optional[str] = None
    openhab_token: Optional[str] = None
    openhab_url: Optional[str] = None
    record_buffer: int = None
    rest_auth_header: Optional[str] = None
    rest_auth_pass: Optional[str] = None
    rest_auth_type: Optional[WillowRestAuthType] = None
    rest_auth_user: Optional[str] = None
    rest_url: Optional[str] = None
    show_prereleases: bool = None
    speaker_volume: int = None
    speech_rec_mode: Optional[WillowSpeechRecMode] = None
    stream_timeout: int = None
    timezone: str = None
    timezone_name: str = None
    vad_mode: int = None
    vad_timeout: int = None
    wake_confirmation: bool = None
    wake_mode: WillowWakeMode = None
    wake_word: WillowWakeWord = None
    was_mode: bool = None
    wis_tts_url: Optional[str] = None
    wis_tts_url_v2: Optional[str] = None
    wis_url: str = None

    # use Enum strings instead of e.g. WillowAudioCodec.PCM
    model_config = ConfigDict(use_enum_values=True)


class WillowNvsWas(BaseModel):
    URL: str = None


class WillowNvsWifi(BaseModel):
    PSK: str = None
    SSID: str = None


class WillowNvsConfig(BaseModel):
    WAS: WillowNvsWas = None
    WIFI: WillowNvsWifi = None
