import asyncio
import json
import time

from logging import getLogger
from pydantic import BaseModel, ConfigDict, Field
from typing import Annotated, Dict, List, Optional

from .connmgr import ConnMgr


log = getLogger("WAS")


class NotifyData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    audio_url: Optional[str] = None
    backlight: bool = False
    backlight_max: bool = False
    cancel: bool = False
    id: int = -1
    repeat: int = 1
    strobe_period_ms: Optional[int] = 0
    text: Optional[str] = None
    volume: Optional[int] = Optional[Annotated[int, Field(ge=0, le=100)]]


class NotifyMsg(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cmd: str = "notify"
    data: NotifyData
    hostname: Optional[str] = None


class NotifyQueue(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    connmgr: ConnMgr = None
    notifications: Dict[str, List[NotifyData]] = {}
    task: asyncio.Task = None

    def start(self):
        loop = asyncio.get_event_loop()
        self.task = loop.create_task(self.dequeue())

    def add(self, msg):
        msg = NotifyMsg.model_validate_json(json.dumps(msg))
        if not hasattr(msg.data, "id") or msg.data.id < 0:
            msg.data.id = int(time.time() * 1000)

        log.debug(msg)

        if msg.hostname is not None:
            mac_addr = self.connmgr.get_mac_by_hostname(msg.hostname)
            if mac_addr == "unknown":
                log.warn(f"no MAC address found for {msg.hostname}, skipping notification")
                return
            if mac_addr in self.notifications:
                self.notifications[mac_addr].append(msg.data)
            else:
                self.notifications.update({mac_addr: [msg.data]})

        else:
            for _, client in self.connmgr.connected_clients.items():
                if client.mac_addr == "unknown":
                    log.warn(f"no MAC address found for {client.hostname}, skipping")
                    continue
                if client.mac_addr in self.notifications:
                    self.notifications[client.mac_addr].append(msg.data)
                else:
                    self.notifications.update({client.mac_addr: [msg.data]})

    def done(self, ws, id):
        client = self.connmgr.get_client_by_ws(ws)
        for i, notification in enumerate(self.notifications[client.mac_addr]):
            if notification.id == id:
                self.connmgr.set_notification_active(ws, 0)
                self.notifications[client.mac_addr].pop(i)
                break

        data = NotifyData(id=id, cancel=True)
        # explicitly set cmd so we can use exclude_unset
        msg_cancel = NotifyMsg(cmd="notify", data=data)
        log.info(msg_cancel)
        asyncio.ensure_future(self.connmgr.broadcast(msg_cancel.model_dump_json(exclude_unset=True)))

    async def dequeue(self):
        while True:
            try:
                for mac_addr, notifications in self.notifications.items():
                    # log.debug(f"dequeueing notifications for {mac_addr}: {notifications} (len={len(notifications)})")
                    if len(notifications) > 0:
                        ws = self.connmgr.get_ws_by_mac(mac_addr)
                        if ws is None:
                            continue
                        if self.connmgr.is_notification_active(ws):
                            log.debug(f"{mac_addr} has active notification")
                            continue

                        for i, notification in enumerate(notifications):
                            if notification.id > int(time.time() * 1000):
                                continue
                            elif notification.id < int((time.time() - 3600) * 1000):
                                # TODO should we make this configurable ?
                                # or at least use a constant and reject notifications with old ID in the API
                                log.warning("expiring notification older than 1h")
                                notifications.pop(i)

                            self.connmgr.set_notification_active(ws, notification.id)
                            log.debug(f"dequeueing notification for {mac_addr}: {notification}")
                            msg = NotifyMsg(data=notification)
                            asyncio.ensure_future(ws.send_text(
                                msg.model_dump_json(exclude={'hostname'}, exclude_none=True))
                            )
                            # don't send more than one notification at once
                            break
            except Exception as e:
                log.debug(f"exception during dequeue: {e}")

            await asyncio.sleep(1)
