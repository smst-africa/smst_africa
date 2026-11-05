"""WebSocket connections for SmSt Stocks.

The shop owner keeps a dashboard open and sees quantities, values and orders
change as they happen. A customer watching a shared product page sees the
stock badge move.
"""

import json
import logging

from channels.generic.websocket import AsyncWebsocketConsumer

logger = logging.getLogger("smst")


class StockShopConsumer(AsyncWebsocketConsumer):
    """The live dashboard of one shop owner."""

    async def connect(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            await self.close()
            return

        self.user = user
        self.group_name = f"smst_stocks_{user.username}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send(text_data=json.dumps({"event": "connected", "data": {}}))

    async def disconnect(self, close_code):
        if getattr(self, "group_name", None):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def stock_event(self, event):
        await self.send(
            text_data=json.dumps(
                {"event": event.get("event", "update"), "data": event.get("data", {})}
            )
        )

    async def receive(self, text_data=None, bytes_data=None):
        """A ping from the browser keeps the connection warm."""
        if not text_data:
            return
        try:
            message = json.loads(text_data)
        except ValueError:
            return
        if message.get("action") == "ping":
            await self.send(text_data=json.dumps({"event": "pong", "data": {}}))


class StockPublicConsumer(AsyncWebsocketConsumer):
    """A customer watching a shared product page."""

    async def connect(self):
        self.product_id = self.scope["url_route"]["kwargs"]["product_id"]
        self.group_name = f"smst_stocks_product_{self.product_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send(text_data=json.dumps({"event": "connected", "data": {}}))

    async def disconnect(self, close_code):
        if getattr(self, "group_name", None):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def stock_event(self, event):
        await self.send(
            text_data=json.dumps(
                {"event": event.get("event", "update"), "data": event.get("data", {})}
            )
        )
