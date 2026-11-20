from django.contrib import messages
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Tool


def home_view(request):
    return render(request, "tools/home.html", {"tools": Tool.objects.all()})


def tool_view(request, name):
    tool = get_object_or_404(Tool, name=name)
    return render(request, "tools/tool.html", {"tool": tool})


@require_POST
def tool_status_update(request, name, status):
    tool = get_object_or_404(Tool, name=name)
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
    return redirect("tool page", name=tool.name)


@require_POST
def tool_maintained(request, name):
    tool = get_object_or_404(Tool, name=name)
    tool.last_maintained = timezone.localdate()
    tool.save(update_fields=["last_maintained"])
    messages.success(request, f"Maintenance on {tool.name} is logged.")
    return redirect("tool page", name=tool.name)
