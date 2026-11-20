from django.contrib import messages
from django.db.models import F
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import NO_AREA_SLUG, Tool


def get_tool(area_slug, tool_slug):
    queryset = Tool.objects.select_related("area")
    if area_slug == NO_AREA_SLUG:
        return get_object_or_404(queryset, area__isnull=True, slug=tool_slug)
    return get_object_or_404(queryset, area__slug=area_slug, slug=tool_slug)


def home_view(request):
    # Grouped by area in the template; tools without an area come last.
    tools = Tool.objects.select_related("area").order_by(
        F("area__name").asc(nulls_last=True), "name"
    )
    return render(request, "tools/home.html", {"tools": tools})


def tool_view(request, area_slug, tool_slug):
    tool = get_tool(area_slug, tool_slug)
    can_edit = request.user.is_staff and tool.can_be_edited_by(request.user)
    return render(request, "tools/tool.html", {"tool": tool, "can_edit": can_edit})


@require_POST
def tool_status_update(request, area_slug, tool_slug, status):
    tool = get_tool(area_slug, tool_slug)
    if status == "down":
        issue = request.POST.get("latest_issue", "").strip()
        if not issue:
            return HttpResponseBadRequest("Please describe the issue")
        tool.functional = False
        tool.latest_issue = issue
        tool.save(update_fields=["functional", "latest_issue"])
        messages.warning(request, f"{tool.name} is marked as not working.")
    elif status == "up":
        tool.functional = True
        tool.save(update_fields=["functional"])
        messages.success(request, f"{tool.name} is marked as working.")
    else:
        return HttpResponseBadRequest("Status must be 'up' or 'down'")
    return redirect(tool)


@require_POST
def tool_maintained(request, area_slug, tool_slug):
    tool = get_tool(area_slug, tool_slug)
    tool.last_maintained = timezone.localdate()
    tool.save(update_fields=["last_maintained"])
    messages.success(request, f"Maintenance on {tool.name} is logged.")
    return redirect(tool)


def legacy_tool_redirect(request, name):
    tool = Tool.objects.select_related("area").filter(name=name).first()
    if tool is None:
        raise Http404("No such tool")
    return redirect(tool, permanent=True)
