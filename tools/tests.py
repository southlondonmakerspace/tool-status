from datetime import date, timedelta
from unittest import mock

from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Tool

TODAY = date(2026, 6, 15)

# The manifest storage needs collectstatic to have run; tests don't need hashed names.
PLAIN_STATIC = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


@mock.patch("tools.models.timezone.localdate", return_value=TODAY)
class ToolModelTests(TestCase):
    def test_next_due_counts_from_last_maintained(self, _):
        tool = Tool(name="Saw", functional=True, last_maintained=date(2026, 1, 1), maintenance_interval=2)
        self.assertEqual(tool.next_due, date(2026, 1, 1) + timedelta(days=60))

    def test_missing_schedule_gives_none(self, _):
        tool = Tool(name="Saw", functional=True)
        self.assertIsNone(tool.next_due)
        self.assertIsNone(tool.days_remaining)
        self.assertFalse(tool.maintenance_overdue)
        self.assertEqual(tool.status, "ok")

    def test_overdue(self, _):
        tool = Tool(name="Saw", functional=True, last_maintained=TODAY - timedelta(days=40), maintenance_interval=1)
        self.assertEqual(tool.days_remaining, -10)
        self.assertEqual(tool.days_overdue, 10)
        self.assertEqual(tool.status, "overdue")

    def test_down_beats_overdue(self, _):
        tool = Tool(name="Saw", functional=False, last_maintained=TODAY - timedelta(days=400), maintenance_interval=1)
        self.assertEqual(tool.status, "down")


@override_settings(STORAGES=PLAIN_STATIC)
class ToolViewTests(TestCase):
    def setUp(self):
        self.tool = Tool.objects.create(name="Band saw", functional=True)

    def test_home_lists_tools_without_a_schedule(self):
        response = self.client.get(reverse("home page"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'href="/Band%20saw"')

    def test_tool_page(self):
        response = self.client.get(reverse("tool page", kwargs={"name": "Band saw"}))
        self.assertEqual(response.status_code, 200)

    def test_unknown_tool_is_404(self):
        response = self.client.get(reverse("tool page", kwargs={"name": "Nope"}))
        self.assertEqual(response.status_code, 404)

    def test_mark_down_requires_an_issue(self):
        url = reverse("update_tool_status", kwargs={"name": "Band saw", "status": "down"})
        response = self.client.post(url, {"latest_issue": "  "})
        self.assertEqual(response.status_code, 400)
        self.tool.refresh_from_db()
        self.assertTrue(self.tool.functional)

    def test_mark_down_and_up(self):
        down = reverse("update_tool_status", kwargs={"name": "Band saw", "status": "down"})
        self.assertRedirects(self.client.post(down, {"latest_issue": "Blade snapped"}), "/Band%20saw")
        self.tool.refresh_from_db()
        self.assertFalse(self.tool.functional)
        self.assertEqual(self.tool.latest_issue, "Blade snapped")

        up = reverse("update_tool_status", kwargs={"name": "Band saw", "status": "up"})
        self.client.post(up)
        self.tool.refresh_from_db()
        self.assertTrue(self.tool.functional)

    def test_unknown_status_is_400(self):
        url = reverse("update_tool_status", kwargs={"name": "Band saw", "status": "sideways"})
        self.assertEqual(self.client.post(url).status_code, 400)

    def test_status_update_rejects_get(self):
        url = reverse("update_tool_status", kwargs={"name": "Band saw", "status": "up"})
        self.assertEqual(self.client.get(url).status_code, 405)

    @mock.patch("tools.views.timezone.localdate", return_value=TODAY)
    def test_log_maintenance(self, _):
        self.client.post(reverse("maintain_tool", kwargs={"name": "Band saw"}))
        self.tool.refresh_from_db()
        self.assertEqual(self.tool.last_maintained, TODAY)

    def test_admin_without_slash_redirects(self):
        self.assertRedirects(
            self.client.get("/admin"), "/admin/", status_code=301, fetch_redirect_response=False
        )


@override_settings(STORAGES=PLAIN_STATIC)
class SiteNameTests(TestCase):
    def test_defaults_to_tool_status(self):
        response = self.client.get(reverse("home page"))
        self.assertContains(response, "<title>Tool Status</title>", html=False)

    @override_settings(SITE_NAME="Woodshop")
    def test_uses_configured_name(self):
        response = self.client.get(reverse("home page"))
        self.assertContains(response, "<title>Woodshop</title>", html=False)


@override_settings(STORAGES=PLAIN_STATIC)
class AreaPermissionTests(TestCase):
    def setUp(self):
        from django.contrib.auth.models import Group, User

        from .models import Area

        self.woodshop = Area.objects.create(name="Woodshop", slug="woodshop")
        self.metal = Area.objects.create(name="Metal shop", slug="metal-shop")
        self.saw = Tool.objects.create(name="Saw", functional=True, area=self.woodshop)
        self.lathe = Tool.objects.create(name="Lathe", functional=True, area=self.metal)

        self.editor = User.objects.create_user("editor", password="x", is_staff=True)
        self.woodshop.editors.add(self.editor)

        self.group_member = User.objects.create_user("member", password="x", is_staff=True)
        group = Group.objects.create(name="Metal shop team")
        group.user_set.add(self.group_member)
        self.metal.editor_groups.add(group)

        self.nobody = User.objects.create_user("nobody", password="x", is_staff=True)
        self.admin = User.objects.create_superuser("admin", password="x")

    def change_url(self, tool):
        return reverse("admin:tools_tool_change", args=[tool.pk])

    def test_editable_by(self):
        from .models import Area

        self.assertEqual(list(Area.objects.editable_by(self.editor)), [self.woodshop])
        self.assertEqual(list(Area.objects.editable_by(self.group_member)), [self.metal])
        self.assertEqual(list(Area.objects.editable_by(self.nobody)), [])
        self.assertEqual(Area.objects.editable_by(self.admin).count(), 2)

    def test_editor_only_sees_their_areas_tools(self):
        self.client.force_login(self.editor)
        response = self.client.get(reverse("admin:tools_tool_changelist"))
        self.assertContains(response, "Saw")
        self.assertNotContains(response, "Lathe")

    def test_editor_can_edit_own_area_but_not_others(self):
        self.client.force_login(self.editor)
        self.assertEqual(self.client.get(self.change_url(self.saw)).status_code, 200)
        # Tools outside the user's areas aren't in their queryset, so the admin
        # redirects to the admin index as if the tool didn't exist.
        self.assertNotEqual(self.client.get(self.change_url(self.lathe)).status_code, 200)

    def test_group_editor_can_edit_group_area(self):
        self.client.force_login(self.group_member)
        self.assertEqual(self.client.get(self.change_url(self.lathe)).status_code, 200)
        self.assertNotEqual(self.client.get(self.change_url(self.saw)).status_code, 200)

    def test_editor_cannot_move_tool_into_another_area(self):
        self.client.force_login(self.editor)
        response = self.client.post(self.change_url(self.saw), {
            "name": "Saw", "area": self.metal.pk, "functional": "on",
        })
        self.assertEqual(response.status_code, 200)  # form re-shown with an error
        self.saw.refresh_from_db()
        self.assertEqual(self.saw.area, self.woodshop)

    def test_staff_without_areas_has_no_tool_access(self):
        self.client.force_login(self.nobody)
        self.assertEqual(self.client.get(reverse("admin:tools_tool_changelist")).status_code, 403)

    def test_editors_cannot_manage_areas(self):
        self.client.force_login(self.editor)
        self.assertEqual(self.client.get(reverse("admin:tools_area_changelist")).status_code, 403)

    def test_superuser_sees_everything(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("admin:tools_tool_changelist"))
        self.assertContains(response, "Saw")
        self.assertContains(response, "Lathe")
