from django.contrib import admin
from django.db.models import Count

from .models import Area, Tool


@admin.register(Area)
class AreaAdmin(admin.ModelAdmin):
    """Only superusers (or users given the Area model permissions) manage areas."""

    list_display = ["name", "slug", "tool_count"]
    readonly_fields = ["slug"]
    filter_horizontal = ["editors", "editor_groups"]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(tool_count=Count("tools"))

    @admin.display(description="Tools", ordering="tool_count")
    def tool_count(self, obj):
        return obj.tool_count


@admin.register(Tool)
class ToolAdmin(admin.ModelAdmin):
    """Superusers, and anyone given a Tool permission in the admin (directly or
    through a group), can do that to every tool. Area editors can see, add,
    edit and delete tools in their own areas, directly or via a group."""

    list_display = ["name", "area", "slug", "functional", "last_maintained", "maintenance_interval"]
    readonly_fields = ["slug"]
    list_filter = ["area", "functional"]
    search_fields = ["name", "description"]

    def editable_areas(self, request):
        if not hasattr(request, "_editable_areas"):
            request._editable_areas = Area.objects.editable_by(request.user)
        return request._editable_areas

    def has_perm_for_all(self, request, action):
        """True if the user has this Tool permission for every area."""
        return request.user.has_perm(f"tools.{action}_tool")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if self.has_perm_for_all(request, "view") or self.has_perm_for_all(request, "change"):
            return qs
        return qs.filter(area__in=self.editable_areas(request))

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "area":
            every_area = self.has_perm_for_all(request, "add") or self.has_perm_for_all(request, "change")
            if not every_area:
                # Area editors must put a tool in one of their areas.
                kwargs["queryset"] = self.editable_areas(request)
                kwargs["required"] = True
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def _has_area_permission(self, request, action, obj=None):
        if self.has_perm_for_all(request, action):
            return True
        if obj is None:
            return self.editable_areas(request).exists()
        return obj.can_be_edited_by(request.user)

    def has_module_permission(self, request):
        return self.has_view_permission(request)

    def has_view_permission(self, request, obj=None):
        return self._has_area_permission(request, "change", obj) or self._has_area_permission(
            request, "view", obj
        )

    def has_change_permission(self, request, obj=None):
        return self._has_area_permission(request, "change", obj)

    def has_delete_permission(self, request, obj=None):
        return self._has_area_permission(request, "delete", obj)

    def has_add_permission(self, request):
        return self._has_area_permission(request, "add")
