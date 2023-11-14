import asyncio
import json
import time

from logging import getLogger
from uuid import uuid4


log = getLogger("WAS")


class WakeEvent:
    def __init__(self, client, volume):
        self.client = client
        self.volume = volume


class WakeSession:
    def __init__(self):
        self.done = False
        self.events = []
        self.id = uuid4()
        self.ts = time.time()
        log.debug(f"WakeSession with ID {self.id} created")

    def add_event(self, event):
        log.debug(f"WakeSession {self.id} adding event {event}")
        self.events.append(event)

    async def cleanup(self, timeout=200):
        await asyncio.sleep(timeout / 1000)
        max_volume = -1000.0
        winner = None
        for event in self.events:
            if event.volume > max_volume:
                max_volume = event.volume
                winner = event.client

        # notify winner first
        await winner.send_text(json.dumps({'wake_result': {'won': True}}))

        for event in self.events:
            if event.client != winner:
                await event.client.send_text(json.dumps({'wake_result': {'won': False}}))

        log.debug(f"Marking WakeSession with ID {self.id} done. Winner: {winner}")
        self.done = True
