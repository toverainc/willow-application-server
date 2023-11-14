import asyncio
import json
import requests
import time
import websockets
from . import (
    CommandEndpoint,
    CommandEndpointResult,
    CommandEndpointRuntimeException,
)


class HomeAssistantWebSocketEndpointNotSupportedException(CommandEndpointRuntimeException):
    pass


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

        self.haws = None

        if not self.is_supported():
            raise HomeAssistantWebSocketEndpointNotSupportedException

        loop = asyncio.get_event_loop()
        self.task = loop.create_task(self.connect())

    def is_supported(self):
        headers = {}
        headers['Content-Type'] = 'application/json'
        headers['Authorization'] = f"Bearer {self.token}"
        ha_components_url = f"{self.construct_url(False)}/api/components"
        response = requests.get(ha_components_url, headers=headers)

        if "assist_pipeline" in response.json():
            return True

        return False

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
                    out.speech = msg["event"]["data"]["intent_output"]["response"]["speech"]["plain"]["speech"]
                    self.log.debug(f"sending {out.__dict__} to {ws}")
                    asyncio.ensure_future(ws.send_text(json.dumps({'result': out.__dict__})))
                    self.connmap.pop(id)
            elif msg["type"] == "auth_required":
                auth_msg = {
                    "type": "auth",
                    "access_token": self.token,
                }
                self.log.debug(f"authenticating HA WebSocket connection: {auth_msg}")
                await self.haws.send(json.dumps(auth_msg))

    def parse_response(self, response):
        return None

    def send(self, jsondata, ws):
        id = int(time.time() * 1000)

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

        self.log.debug(f"sending to HA WS: {out}")
        asyncio.ensure_future(self.haws.send(json.dumps(out)))

    def stop(self):
        self.log.info(f"stopping {self.name}")
        self.task.cancel()
