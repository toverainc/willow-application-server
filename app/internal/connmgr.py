import logging

from fastapi import (
    WebSocket,
    WebSocketException,
)
from typing import Dict

from .client import Client


log = logging.getLogger("WAS")


class ConnMgr:
    def __init__(self):
        self.connected_clients: Dict[WebSocket, Client] = {}

    async def accept(self, ws: WebSocket, client: Client):
        try:
            await ws.accept()
            self.connected_clients[ws] = client
        except WebSocketException as e:
            log.error(f"Failed to accept websocket connection: {e}")

    async def broadcast(self, msg: str):
        for client in self.connected_clients:
            try:
                await client.send_text(msg)
            except Exception as e:
                log.error(f"Failed to broadcast message: {e}")

    def disconnect(self, ws: WebSocket):
        if ws in self.connected_clients:
            self.connected_clients.pop(ws)

    def get_client_by_hostname(self, hostname):
        for k, v in self.connected_clients.items():
            if v.hostname == hostname:
                return k

    def get_client_by_ws(self, ws):
        return self.connected_clients[ws]

    def get_mac_by_hostname(self, hostname):
        for k, v in self.connected_clients.items():
            if v.hostname == hostname:
                return v.mac_addr

        return None

    def get_ws_by_mac(self, mac):
        for k, v in self.connected_clients.items():
            # log.debug(f"get_ws_by_mac: {k} {v.mac_addr}")
            if v.mac_addr == mac:
                return k

        log.debug("get_ws_by_mac: returning None")
        return None

    def is_notification_active(self, ws):
        return self.connected_clients[ws].is_notification_active()

    def set_notification_active(self, ws, id):
        self.connected_clients[ws].set_notification_active(id)

    def update_client(self, ws, key, value):
        if key == "hostname":
            self.connected_clients[ws].set_hostname(value)
        elif key == "platform":
            self.connected_clients[ws].set_platform(value)
        elif key == "mac_addr":
            self.connected_clients[ws].set_mac_addr(value)
