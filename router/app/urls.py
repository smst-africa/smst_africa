from django.urls import include, path
from django.views.i18n import JavaScriptCatalog
from .views import *
urlpatterns = [
    path('', app, name="appHomePage"),
    path('app/', smst_app, name="smst_app"),
    # SmSt Stocks opens on /smst_stocks/ and carries its own API.
    path('smst_stocks/', include('smst_stocks.urls')),
    # SmSt Finances opens on /smst_finances/ and carries its own API.
    path('smst_finances/', include('smst_finances.urls')),
    # SmSt Works opens on /smst_works/ and carries its own API.
    path('smst_works/', include('smst_works.urls')),
    # Adverts sit across every SmSt app; this is where they are managed.
    path('smst_adverts/', include('smst_adverts.urls')),
    path('login/', login, name="login"),
    path("i18n/", include("django.conf.urls.i18n")),
    path("jsi18n/", JavaScriptCatalog.as_view(), name="javascript-catalog"),

]
