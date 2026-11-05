from django.urls import path, include
from .views import *
from django.views.i18n import JavaScriptCatalog
urlpatterns = [
    path('', include('pwa.urls')),
    path("", user, name="user"),
    path("cake", cake, name="cake"),
    path('accounts/profile/', profile, name="user"),
    path('accounts/', include('allauth.urls')),
    path("i18n/", include("django.conf.urls.i18n")),
    path("jsi18n/", JavaScriptCatalog.as_view(), name="javascript-catalog"),
    path('webhook/', webhook, name="webhook")
]