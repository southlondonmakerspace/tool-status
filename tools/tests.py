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
