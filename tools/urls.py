from django.urls import path

from . import views

TOOL = "<slug:area_slug>/<slug:tool_slug>"

urlpatterns = [
    path("", views.home, name="home"),
    path(TOOL, views.tool_detail, name="tool"),
    path(f"{TOOL}/report", views.report_problem, name="report_problem"),
    path(f"{TOOL}/fixed", views.mark_working, name="mark_working"),
    path(f"{TOOL}/maintained", views.log_maintenance, name="log_maintenance"),
    # Old links used the tool's name, such as /Band%20saw.
    path("<str:name>", views.legacy_tool_redirect, name="legacy_tool"),
]
