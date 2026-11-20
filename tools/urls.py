from django.urls import path

from . import views

tool = "<slug:area_slug>/<slug:tool_slug>"

urlpatterns = [
    path("", views.home_view, name="home page"),
    path(tool, views.tool_view, name="tool page"),
    path(f"{tool}/status/<str:status>", views.tool_status_update, name="update_tool_status"),
    path(f"{tool}/maintained", views.tool_maintained, name="maintain_tool"),
    # Old links used the tool's name, such as /Band%20saw.
    path("<str:name>", views.legacy_tool_redirect, name="legacy tool page"),
]
