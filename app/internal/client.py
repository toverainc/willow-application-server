from pydantic import BaseModel


class Client(BaseModel):
    hostname: str = "unknown"
    platform: str = "unknown"
    mac_addr: str = "unknown"
    notification_active: int = 0
    ua: str = None

    def set_hostname(self, hostname):
        self.hostname = hostname

    def set_platform(self, platform):
        self.platform = platform

    def set_mac_addr(self, mac_addr):
        self.mac_addr = mac_addr

    def is_notification_active(self):
        return self.notification_active != 0

    def set_notification_active(self, id):
        self.notification_active = id
