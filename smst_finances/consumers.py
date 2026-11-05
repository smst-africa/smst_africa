"""WebSocket connections for SmSt Finances."""

import json
import logging

from channels.generic.websocket import AsyncWebsocketConsumer

logger = logging.getLogger("smst")


class FinanceShopConsumer(AsyncWebsocketConsumer):
    """The live money dashboard of one shop owner."""

    async def connect(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            await self.close()
            return

        self.user = user
        self.group_name = f"smst_finances_{user.username}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send(text_data=json.dumps({"event": "connected", "data": {}}))

    async def disconnect(self, close_code):
        if getattr(self, "group_name", None):
            await self.channel_layer.group_discard(
                self.group_name, self.channel_name
            )

    async def finance_event(self, event):
        await self.send(
            text_data=json.dumps(
                {"event": event.get("event", "update"), "data": event.get("data", {})}
            )
        )

    async def receive(self, text_data=None, bytes_data=None):
        if not text_data:
            return
        try:
            message = json.loads(text_data)
        except ValueError:
            return
        if message.get("action") == "ping":
            await self.send(text_data=json.dumps({"event": "pong", "data": {}}))
