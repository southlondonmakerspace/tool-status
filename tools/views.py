from django.shortcuts import render
from django.http import HttpResponse

from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt

from django.shortcuts import get_object_or_404, redirect


from .models import Tool
import json

from datetime import timedelta, datetime, date

# Create your views here.
def home_view(request):
    tools = Tool.objects.all()
    for tool in tools:
        tool.needs_maintainance=  (date.today()+ timedelta(tool.maintenance_interval*30)).strftime("%Y-%m-%d")
        tool.remaining_time = ((tool.last_maintained + timedelta(tool.maintenance_interval * 30)) - date.today())

    context = {"tools":tools}
    return render(request, "tools/home.html", context)

def tool_view(request, name):
    tool = Tool.objects.get(name=name)
    tool.needs_maintainance =  (tool.last_maintained + timedelta(tool.maintenance_interval*30)).strftime("%Y-%m-%d")
    tool.remaining_time = ((tool.last_maintained + timedelta(tool.maintenance_interval * 30)) - date.today())
    context = {"tool":tool}
    return render(request, "tools/tool.html", context)

@require_http_methods(["POST"])
def tool_status_update(request, name, status):
    tool = Tool.objects.get(name=name)
    if status == "down":
        issue = request.POST.get("latest_issue", "").strip()
        if not issue:
            return HttpResponseBadRequest("Please provide latest_issue")
        tool.functional = False
        tool.latest_issue = issue
        response = HttpResponse("The tool is now down")
        tool.save(update_fields=["functional","latest_issue"])
    elif status == "up":
        tool.functional = True
        response = HttpResponse("The tool is now up")
        tool.save(update_fields=["functional"])
    return redirect("tool page", name=name)

@require_http_methods(["POST"])
def tool_maintained(request, name):
    tool = Tool.objects.get(name=name)
    Needs_maintainance = (datetime.now() + timedelta(tool.maintenance_interval*30)).strftime("%Y-%m-%d")
    tool.last_maintained = datetime.now().strftime("%Y-%m-%d")
    tool.save(update_fields=["last_maintained"])
    return redirect("tool page", name=name) 
