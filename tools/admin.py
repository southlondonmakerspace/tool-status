from django.contrib import admin

from .models import Area, Tool


@admin.register(Area)
class AreaAdmin(admin.ModelAdmin):
    """Only superusers (or users given the Area model permissions) manage areas."""

    list_display = ["name", "slug", "tool_count"]
    prepopulated_fields = {"slug": ["name"]}
    filter_horizontal = ["editors", "editor_groups"]

    @admin.display(description="Tools")
    def tool_count(self, obj):
        return obj.tools.count()


@admin.register(Tool)
class ToolAdmin(admin.ModelAdmin):
    """Superusers can edit every tool. Other staff can only see, add, edit and
    delete tools in the areas they're an editor of, directly or via a group."""

    list_display = ["name", "area", "functional", "last_maintained", "maintenance_interval"]
    list_filter = ["area", "functional"]
    search_fields = ["name", "description"]

    def editable_areas(self, request):
        if not hasattr(request, "_editable_areas"):
            request._editable_areas = Area.objects.editable_by(request.user)
        return request._editable_areas

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(area__in=self.editable_areas(request))

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "area":
            kwargs["queryset"] = self.editable_areas(request)
            # Everyone but superusers must put a tool in one of their areas.
            kwargs["required"] = not request.user.is_superuser
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def _has_area_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        if obj is None:
            return self.editable_areas(request).exists()
        return obj.can_be_edited_by(request.user)

    def has_module_permission(self, request):
        return self._has_area_permission(request)

    def has_view_permission(self, request, obj=None):
        return self._has_area_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        return self._has_area_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return self._has_area_permission(request, obj)

    def has_add_permission(self, request):
        return self._has_area_permission(request)
