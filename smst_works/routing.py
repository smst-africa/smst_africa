"""WebSocket routes for SmSt Works."""

from django.urls import re_path

from . import consumers

websocket_urlpatterns = [
    re_path(
        r"^ws/smst_works/shop/$",
        consumers.WorksShopConsumer.as_asgi(),
    ),
]
