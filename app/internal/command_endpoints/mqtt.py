import asyncio
import json
import logging
import paho.mqtt.client as mqtt
from . import (
    CommandEndpoint,
    CommandEndpointConfigException,
    CommandEndpointResponse,
    CommandEndpointResult,
    CommandEndpointRuntimeException
)
from enum import Enum


class MqttAuthType(Enum):
    NONE = 1
    USERPW = 2


class MqttConfig:
    auth_type: Enum = MqttAuthType.NONE
    hostname: str = None
    password: str = None
    port: int = 8883
    tls: bool = True
    topic: str = None
    username: str = None

    log = logging.getLogger("WAS")

    def set_auth_type(self, auth_type=MqttAuthType.NONE):
        self.log.debug(f"setting auth type: {auth_type}")
        self.auth_type = MqttAuthType[auth_type.upper()]

    def set_hostname(self, hostname=None):
        self.hostname = hostname

    def set_password(self, password=None):
        self.password = password

    def set_port(self, port=8883):
        self.port = port

    def set_tls(self, tls=True):
        self.tls = tls

    def set_topic(self, topic=None):
        self.topic = topic

    def set_username(self, username=None):
        self.username = username

    def validate(self):
        if self.auth_type == MqttAuthType.USERPW:
            if self.password is None:
                raise CommandEndpointConfigException("User/Password auth enabled without password")
            if self.username is None:
                raise CommandEndpointConfigException("User/Password auth enabled without password")


class MqttEndpoint(CommandEndpoint):
    name = "MQTT"

    def __init__(self, config):
        self.config = config
        self.config.validate()
        self.connected = False
        self.mqtt_client = None

        loop = asyncio.get_event_loop()
        self.task = loop.create_task(self.connect())

    async def connect(self):
        try:
            self.mqtt_client = mqtt.Client()
            self.mqtt_client.on_connect = self.cb_connect
            self.mqtt_client.on_disconnect = self.cb_disconnect
            self.mqtt_client.on_msg = self.cb_msg
            if self.config.username is not None and self.config.password is not None:
                self.mqtt_client.username_pw_set(self.config.username, self.config.password)
            if self.config.tls:
                self.mqtt_client.tls_set()
            self.mqtt_client.connect_async(self.config.hostname, self.config.port, 60)
            self.mqtt_client.loop_start()
        except Exception as e:
            self.log.info(f"{self.name}: exception occurred: {e}")
            await asyncio.sleep(1)

    def cb_connect(self, client, userdata, flags, rc):
        self.connected = True
        self.log.info("MQTT connected")
        client.subscribe(self.config.topic)

    def cb_disconnect(self, client, userdata, rc):
        self.connected = False
        self.log.info("MQTT disconnected")

    def cb_msg(self, client, userdata, msg):
        self.log.info(f"cb_msg: topic={msg.topic} payload={msg.payload}")

    def parse_response(self, response):
        res = CommandEndpointResult()
        if response.ok:
            res.ok = True
            if len(res.speech) > 0:
                res.speech = response.text
            else:
                res.speech = "Success!"

        command_endpoint_response = CommandEndpointResponse(result=res)
        return command_endpoint_response.model_dump_json()

    def send(self, data=None, jsondata=None, ws=None, client=None):
        if not self.connected:
            raise CommandEndpointRuntimeException(f"{self.name} not connected")
        try:
            if jsondata is not None:
                self.mqtt_client.publish(self.config.topic, payload=json.dumps(jsondata))
            else:
                self.mqtt_client.publish(self.config.topic, payload=data)
        except Exception as e:
            raise CommandEndpointRuntimeException(e)
