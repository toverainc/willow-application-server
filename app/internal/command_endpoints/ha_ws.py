import asyncio
import json
import requests
import time
import websockets
from . import (
    CommandEndpoint,
    CommandEndpointResponse,
    CommandEndpointResult,
    CommandEndpointRuntimeException,
)


class HomeAssistantWebSocketEndpoint(CommandEndpoint):
    name = "WAS Home Assistant WebSocket Endpoint"

    connmap = {}

    def __init__(self, app, host, port, tls, token):

        self.app = app
        self.host = host
        self.port = port
        self.token = token
        self.tls = tls
        self.url = self.construct_url(ws=True)

        self.ha_willow_devices = {}
        self.ha_willow_devices_request_id = None
        self.haws = None

        loop = asyncio.get_event_loop()
        self.task = loop.create_task(self.connect())

    def construct_url(self, ws):
        ha_url_scheme = ""
        if ws:
            ha_url_scheme = "wss://" if self.tls else "ws://"
        else:
            ha_url_scheme = "https://" if self.tls else "http://"

        return f"{ha_url_scheme}{self.host}:{self.port}"

    async def connect(self):
        while True:
            try:
                # deflate compression is enabled by default, making tcpdump difficult
                async with websockets.connect(f"{self.url}/api/websocket", compression=None) as self.haws:
                    while True:
                        msg = await self.haws.recv()
                        await self.cb_msg(msg)
            except Exception as e:
                self.log.info(f"{self.name}: exception occurred: {e}")
                await asyncio.sleep(1)

    async def cb_msg(self, msg):
        self.log.debug(f"haws_cb: {self.app} {msg}")
        msg = json.loads(msg)
        if "type" in msg:
            if msg["type"] == "event":
                if msg["event"]["type"] == "intent-end":
                    id = int(msg["id"])
                    ws = self.connmap[id]
                    out = CommandEndpointResult()
                    response_type = msg["event"]["data"]["intent_output"]["response"]["response_type"]
                    if response_type == "action_done":
                        out.ok = True
                    response = msg["event"]["data"]["intent_output"]["response"]
                    # Not all intents return speech (e.g. HassNeverMind)
                    if 'plain' in response["speech"]:
                        out.speech = response["speech"]["plain"]["speech"]
                    else:
                        out.speech = ""
                    command_endpoint_response = CommandEndpointResponse(result=out)
                    self.log.debug(f"sending {command_endpoint_response} to {ws}")
                    asyncio.ensure_future(ws.send_text(command_endpoint_response.model_dump_json()))
                    self.connmap.pop(id)
            elif msg["type"] == "auth_required":
                auth_msg = {
                    "type": "auth",
                    "access_token": self.token,
                }
                self.log.debug(f"authenticating HA WebSocket connection: {auth_msg}")
                await self.haws.send(json.dumps(auth_msg))
            elif msg["type"] == "auth_ok":
                self.ha_willow_devices_request_id = self.next_id()
                msg = {
                    "type": "config/device_registry/list",
                    "id": self.ha_willow_devices_request_id
                }
                self.log.debug(f"fetching devices: {msg}")
                await self.haws.send(json.dumps(msg))
            elif msg["type"] == "result" and msg["success"]:
                if msg["id"] == self.ha_willow_devices_request_id:
                    devices = msg["result"]
                    self.ha_willow_devices = {
                        ident[1]: item["id"]
                        for item in devices
                        for ident in item.get("identifiers", [])
                        if ident[0] == "willow"
                    }
                    self.log.debug(f"received willow devics: {self.ha_willow_devices}")

    def parse_response(self, response):
        return None

    def next_id(self):
        return int(time.monotonic_ns())

    def send(self, jsondata, ws, client=None):
        id = self.next_id()

        if id not in self.connmap:
            self.connmap[id] = ws

        if "language" in jsondata:
            jsondata.pop("language")

        out = {
            'end_stage': 'intent',
            'id': id,
            'input': jsondata,
            'start_stage': 'intent',
            'type': 'assist_pipeline/run',
        }

        if client.mac_addr in self.ha_willow_devices:
            self.log.info("HA has a registered device for this willow satellite")
            out["device_id"] = self.ha_willow_devices[client.mac_addr]

        self.log.debug(f"sending to HA WS: {out}")
        asyncio.ensure_future(self.haws.send(json.dumps(out)))

    def stop(self):
        self.log.info(f"stopping {self.name}")
        self.task.cancel()
