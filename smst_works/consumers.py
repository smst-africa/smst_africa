"""WebSocket connections for SmSt Works."""

import json
import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

logger = logging.getLogger("smst")


class WorksShopConsumer(AsyncWebsocketConsumer):
    """The live shop floor of every shop a person belongs to."""

    async def connect(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            await self.close()
            return

        self.user = user
        self.groups = [
            f"smst_works_shop_{shop_id}"
            for shop_id in await database_sync_to_async(self._shop_ids)()
        ]
        for group in self.groups:
            await self.channel_layer.group_add(group, self.channel_name)
        await self.accept()
        await self.send(
            text_data=json.dumps(
                {
                    "event": "connected",
                    "data": {"shops": [g.rsplit("_", 1)[-1] for g in self.groups]},
                }
            )
        )

    def _shop_ids(self):
        from .services import shops_for

        return list(shops_for(self.user).values_list("id", flat=True))

    async def disconnect(self, close_code):
        for group in getattr(self, "groups", []):
            await self.channel_layer.group_discard(group, self.channel_name)

    async def works_event(self, event):
        await self.send(
            text_data=json.dumps(
                {
                    "event": event.get("event", "works.updated"),
                    "data": event.get("data", {}),
                }
            )
        )

    async def receive(self, text_data=None, bytes_data=None):
        if not text_data:
            return
        try:
            payload = json.loads(text_data)
        except ValueError:
            return
        if payload.get("event") == "ping":
            await self.send(
                text_data=json.dumps({"event": "pong", "data": {}})
            )
