from .rest import RestAuthType, RestConfig, RestEndpoint


class OpenhabEndpoint(RestEndpoint):
    name = "WAS openHAB Endpoint"

    def __init__(self, url, token):
        self.config = RestConfig(auth_type=RestAuthType.BASIC, auth_user=token)
        self.url = f"{url}/rest/voice/interpreters"

    def send(self, jsondata=None, ws=None):
        return super().send(data=jsondata["text"])
