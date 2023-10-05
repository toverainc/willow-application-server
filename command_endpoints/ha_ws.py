import asyncio
import json
import time
import websockets
from . import (
    CommandEndpoint,
    CommandEndpointConfigException,
    CommandEndpointResult,
    CommandEndpointRuntimeException,
)


class HomeAssistantWebSocketEndpoint(CommandEndpoint):
    name = "WAS Home Assistant WebSocket Endpoint"

    connmap = {}

    def __init__(self, app, url, token):
        self.app = app
        self.token = token
        self.url = url
        self.haws = None

        loop = asyncio.get_event_loop()
        self.task = loop.create_task(self.connect())
        # TODO reconnect when changing endpoint settings
        # app.haws_task.cancel()

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
        id = int(time.time())

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