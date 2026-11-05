"""Support centre routes.

The hub lists the three apps. Every app carries its own support page with
manuals, tips and release notes.
"""

from django.urls import path

from . import views

app_name = "smst_support"

urlpatterns = [
    path("", views.hub, name="hub"),
    path("<slug:slug>/", views.app, name="app"),
]
