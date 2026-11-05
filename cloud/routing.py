from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r"ws/user/$", consumers.SmstConsumer.as_asgi()),
    re_path(r"ws/smst_app/$", consumers.SmstAppConsumer.as_asgi())
]

# The SmSt Stocks app keeps the dashboard and the shared pages up to date.
# asgi.py reads the websocket routes from this module.
try:
    from smst_stocks.routing import (
        websocket_urlpatterns as smst_stocks_websocket_urlpatterns,
    )

    websocket_urlpatterns = websocket_urlpatterns + smst_stocks_websocket_urlpatterns
except ImportError:  # pragma: no cover - the app is optional
    pass

# The SmSt Finances app pushes each money change to the owner's dashboard.
try:
    from smst_finances.routing import (
        websocket_urlpatterns as smst_finances_websocket_urlpatterns,
    )

    websocket_urlpatterns = websocket_urlpatterns + smst_finances_websocket_urlpatterns
except ImportError:  # pragma: no cover - the app is optional
    pass

# The SmSt Works app keeps every member of a shop on the same live timeline.
try:
    from smst_works.routing import (
        websocket_urlpatterns as smst_works_websocket_urlpatterns,
    )

    websocket_urlpatterns = websocket_urlpatterns + smst_works_websocket_urlpatterns
except ImportError:  # pragma: no cover - the app is optional
    pass
