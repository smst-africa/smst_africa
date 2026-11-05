"""WebSocket routes for SmSt Stocks."""

from django.urls import re_path

from . import consumers

websocket_urlpatterns = [
    re_path(
        r"^ws/smst_stocks/shop/$",
        consumers.StockShopConsumer.as_asgi(),
    ),
    re_path(
        r"^ws/smst_stocks/product/(?P<product_id>\d+)/$",
        consumers.StockPublicConsumer.as_asgi(),
    ),
]
