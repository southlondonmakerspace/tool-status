from django.contrib import admin

from .models import Area, Tool


@admin.register(Area)
class AreaAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "tool_count"]
    prepopulated_fields = {"slug": ["name"]}
    filter_horizontal = ["editors", "editor_groups"]

    @admin.display(description="Tools")
    def tool_count(self, obj):
        return obj.tools.count()


@admin.register(Tool)
class ToolAdmin(admin.ModelAdmin):
    list_display = ["name", "area", "functional", "last_maintained", "maintenance_interval"]
    list_filter = ["area", "functional"]
    search_fields = ["name", "description"]
