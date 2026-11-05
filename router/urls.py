from django.urls import include, path
from .views import *

urlpatterns = [
    # The redesigned SmSt Africa site is mounted first so that it owns the
    # root of the marketing host. The legacy routes stay below it.
    path("", frontend, name="frontend"),
    path("<snippet>", snippet_access, name="access_snippets"),
    path('users/', user_access, name="user_access"),
    path('docs/<doc>', documentation_access, name="docs")
]

