import asyncio
import json
import requests
import time
import websockets

from copy import copy

from jsonget import json_get, json_get_default

from app.internal.openai import openai_chat
from app.internal.wac import FEEDBACK, wac_add, wac_search
from . import (
    CommandEndpoint,
    CommandEndpointResponse,
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
                    command = self.connmap[id]["jsondata"]["text"]
                    ws = self.connmap[id]["ws"]
                    out = CommandEndpointResult()
                    # not all responses contain speech but default in the pydantic model is "Error"
                    out.speech = json_get_default(msg, "/event/data/intent_output/response/speech/plain/speech", "")
                    response_type = json_get(msg, "/event/data/intent_output/response/response_type")
                    if response_type in ["action_done", "query_answer"]:
                        out.ok = True

                        if self.app.wac_enabled:
                            learned = wac_add(command, rank=0.9, source='autolearn')

                            if learned is True and FEEDBACK is True:
                                out.speech = f"{out.speech} and learned command"

                    elif response_type == "error":
                        response_code = json_get(msg, "/event/data/intent_output/response/data/code")
                        if response_code in ["no_intent_match", "no_valid_targets"]:
                            self.log.debug(self.connmap[id])

                            if self.app.wac_enabled:
                                if self.connmap[id]["final"]:
                                    return
                                wac_success, wac_command = wac_search(command)

                                if wac_success:
                                    jsondata = self.connmap[id]["jsondata"]
                                    jsondata["text"] = wac_command
                                    self.send(jsondata, ws, True)
                                    self.connmap.pop(id)
                                    return
                                else:
                                    out.speech = openai_chat(command)

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

    def parse_response(self, response):
        return None

    def send(self, jsondata, ws, final=False):
        id = int(time.time() * 1000)

        if id not in self.connmap:
            self.connmap[id] = {
                'final': final,
                'jsondata': copy(jsondata),
                'ws': ws,
            }

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
