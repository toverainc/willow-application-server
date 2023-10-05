import json
from . import CommandEndpointResult
from .rest import RestAuthType, RestConfig, RestEndpoint


class HomeAssistantRestEndpoint(RestEndpoint):
    name = "WAS Home Assistant REST Endpoint"

    def __init__(self, url, token):
        self.config = RestConfig(auth_type=RestAuthType.HEADER, auth_header=f"Bearer {token}")
        self.url = f"{url}/api/conversation/process"

    def get_speech(self, data):
        speech = data["response"]["speech"]["plain"]["speech"]
        return speech

    def parse_response(self, response):
        res = CommandEndpointResult()
        if response.ok:
            res.ok = True
            res.speech = self.get_speech(response.json())

        return json.dumps({'result': res.__dict__})
