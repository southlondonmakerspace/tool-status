from django.contrib import messages
from django.db.models import F
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import ReportProblemForm
from .models import NO_AREA_SLUG, Tool


def get_tool(area_slug, tool_slug):
    tools = Tool.objects.select_related("area")
    if area_slug == NO_AREA_SLUG:
        return get_object_or_404(tools, area__isnull=True, slug=tool_slug)
    return get_object_or_404(tools, area__slug=area_slug, slug=tool_slug)


def render_tool(request, tool, form=None, status=200):
    context = {
        "tool": tool,
        "form": form or ReportProblemForm(),
        "can_edit": request.user.is_staff and tool.can_be_edited_by(request.user),
    }
    return render(request, "tools/tool.html", context, status=status)


def home(request):
    # Grouped by area in the template; tools without an area come last.
    tools = Tool.objects.select_related("area").order_by(F("area__name").asc(nulls_last=True), "name")
    return render(request, "tools/home.html", {"tools": tools})


def tool_detail(request, area_slug, tool_slug):
    return render_tool(request, get_tool(area_slug, tool_slug))


@require_POST
def report_problem(request, area_slug, tool_slug):
    tool = get_tool(area_slug, tool_slug)
    form = ReportProblemForm(request.POST)
    if not form.is_valid():
        return render_tool(request, tool, form=form, status=400)
    tool.functional = False
    tool.latest_issue = form.cleaned_data["latest_issue"]
    tool.save(update_fields=["functional", "latest_issue"])
    messages.warning(request, f"{tool.name} is marked as not working.")
    return redirect(tool)


@require_POST
def mark_working(request, area_slug, tool_slug):
    tool = get_tool(area_slug, tool_slug)
    tool.functional = True
    tool.save(update_fields=["functional"])
    messages.success(request, f"{tool.name} is marked as working.")
    return redirect(tool)


@require_POST
def log_maintenance(request, area_slug, tool_slug):
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
