"""Public landing pages for the SmSt Apps."""

from django.urls import path, include
from django.views.i18n import JavaScriptCatalog

from . import views

app_name = "smst_app"

urlpatterns = [
    # SmSt Stocks is a SmSt App. It lives under the app host and opens on
    # /smst_stocks/.
    path("smst_stocks/", include("smst_stocks.urls")),
    # SmSt Finances carries the money book and its own API.
    path("smst_finances/", include("smst_finances.urls")),
    # SmSt Works runs the team, the shop floor and the live job timeline.
    path("smst_works/", include("smst_works.urls")),
    # Adverts sit across every SmSt app; this is where they are managed.
    path("smst_adverts/", include("smst_adverts.urls")),
    path("i18n/", include("django.conf.urls.i18n")),
    path("jsi18n/", JavaScriptCatalog.as_view(), name="javascript-catalog"),
]
