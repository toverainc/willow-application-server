import json
import logging
from . import (
    CommandEndpoint,
    CommandEndpointConfigException,
    CommandEndpointResponse,
    CommandEndpointResult,
    CommandEndpointRuntimeException
)
from enum import Enum
from requests import request
from requests.auth import HTTPBasicAuth


class RestAuthType(Enum):
    NONE = 1
    BASIC = 2
    HEADER = 3


class RestConfig():
    auth_header: str = ""
    auth_pass: str = ""
    auth_type: Enum = RestAuthType.NONE
    auth_user: str = ""

    log = logging.getLogger("WAS")

    def __init__(self, auth_type=RestAuthType.NONE, auth_header="", auth_pass="", auth_user=""):
        self.auth_header = auth_header
        self.auth_pass = auth_pass
        self.auth_type = auth_type
        self.auth_user = auth_user

    def set_auth_header(self, auth_header=""):
        self.log.debug(f"setting auth header: {auth_header}")
        self.auth_header = auth_header

    def set_auth_pass(self, auth_pass=""):
        self.log.debug(f"setting auth password: {auth_pass}")
        self.auth_pass = auth_pass

    def set_auth_type(self, auth_type=RestAuthType.NONE):
        self.log.debug(f"setting auth type: {auth_type}")
        self.auth_type = RestAuthType[auth_type.upper()]

    def set_auth_user(self, auth_user=""):
        self.log.debug(f"setting auth username: {auth_user}")
        self.auth_user = auth_user


class RestEndpoint(CommandEndpoint):
    name = "REST"

    def __init__(self, url):
        self.config = RestConfig()
        self.url = url

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
        try:
            basic = None
            headers = {}

            if jsondata is not None:
                headers['Content-Type'] = 'application/json'
            else:
                headers['Content-Type'] = 'text/plain'

            if self.config.auth_type == RestAuthType.BASIC:
                basic = HTTPBasicAuth(self.config.auth_user, self.config.auth_pass)
            elif self.config.auth_type == RestAuthType.HEADER:
                headers['Authorization'] = self.config.auth_header
            elif self.config.auth_type == RestAuthType.NONE:
                pass
            else:
                raise CommandEndpointConfigException("invalid REST auth type")

            return request("POST", self.url, auth=basic, data=data, headers=headers, json=jsondata, timeout=(1, 30))

        except Exception as e:
            raise CommandEndpointRuntimeException(e)
