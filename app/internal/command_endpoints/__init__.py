import logging

from pydantic import BaseModel

class CommandEndpointConfigException(Exception):
    """Raised when an the command endpoint configuration is invalid

    Attributes:
        msg -- error message
    """

    def __init__(self, msg="Command Endpoint configuration is invalid"):
        self.msg = msg
        super().__init__(self.msg)


class CommandEndpointRuntimeException(Exception):
    """"Raised when an exception occurs while contacting the command endpoint

    Attributes:
        msg -- error message
    """

    def __init__(self, msg="Runtime exception occured in Command Endpoint"):
        self.msg = msg
        super().__init__(self.msg)


class CommandEndpointResult(BaseModel):
    ok: bool = False
    speech: str = "Error!"


class CommandEndpointResponse(BaseModel):
    result: CommandEndpointResult = None


class CommandEndpoint():
    name = "WAS CommandEndpoint"
    log = logging.getLogger("WAS")
