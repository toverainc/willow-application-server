import logging


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


class CommandEndpointResult():
    ok: bool = False
    speech: str = ""

    def __init__(self):
        self.ok = False
        self.speech = "Error!"


class CommandEndpoint():
    name = "WAS CommandEndpoint"
    log = logging.getLogger("WAS")
