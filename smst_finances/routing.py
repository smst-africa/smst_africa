"""WebSocket routes for SmSt Finances."""

from django.urls import re_path

from . import consumers

websocket_urlpatterns = [
    re_path(
        r"^ws/smst_finances/shop/$",
        consumers.FinanceShopConsumer.as_asgi(),
    ),
]
