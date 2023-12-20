class Client:
    def __init__(self, ua):
        self.hostname = "unknown"
        self.platform = "unknown"
        self.mac_addr = "unknown"
        self.srmodels = []
        self.ua = ua
        self.notification_active = 0

    def set_hostname(self, hostname):
        self.hostname = hostname

    def set_platform(self, platform):
        self.platform = platform

    def set_mac_addr(self, mac_addr):
        self.mac_addr = mac_addr

    def set_srmodels(self, srmodels):
        self.srmodels = srmodels

    def is_notification_active(self):
        return self.notification_active != 0

    def set_notification_active(self, id):
        self.notification_active = id
