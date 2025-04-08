import json
from . import CommandEndpointResponse, CommandEndpointResult
from .rest import RestAuthType, RestConfig, RestEndpoint


class HomeAssistantRestEndpoint(RestEndpoint):
    name = "WAS Home Assistant REST Endpoint"

    def __init__(self, host, port, tls, token):
        self.host = host
        self.port = port
        self.token = token
        self.tls = tls
        self.url = self.construct_url(ws=False)
        self.config = RestConfig(auth_type=RestAuthType.HEADER, auth_header=f"Bearer {token}")

    def construct_url(self, ws):
        ha_url_scheme = ""
        if ws:
            ha_url_scheme = "wss://" if self.tls else "ws://"
        else:
            ha_url_scheme = "https://" if self.tls else "http://"

        return f"{ha_url_scheme}{self.host}:{self.port}/api/conversation/process"

    def get_speech(self, data):
        if 'plain' in data["response"]["speech"]:
            return data["response"]["speech"]["plain"]["speech"]
        else:
            return ""

    def parse_response(self, response):
        res = CommandEndpointResult()
        if response.ok:
            res.ok = True
            res.speech = self.get_speech(response.json())

        command_endpoint_response = CommandEndpointResponse(result=res)
        return command_endpoint_response.model_dump_json()

    def send(self, data=None, jsondata=None, ws=None):
        out = {'text': jsondata["text"], 'language': jsondata["language"]}
        return super().send(jsondata=out)
