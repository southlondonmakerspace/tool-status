from datetime import date, timedelta
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth.models import Group, User
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from allauth.account.signals import user_logged_in

from .models import Area, Status, Tool
from .sso import group_names_from

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
        self.assertEqual(tool.status, Status.OK)

    def test_overdue(self, _):
        tool = Tool(name="Saw", functional=True, last_maintained=TODAY - timedelta(days=40), maintenance_interval=1)
        self.assertEqual(tool.days_remaining, -10)
        self.assertEqual(tool.days_overdue, 10)
        self.assertEqual(tool.status, Status.OVERDUE)

    def test_down_beats_overdue(self, _):
        tool = Tool(name="Saw", functional=False, last_maintained=TODAY - timedelta(days=400), maintenance_interval=1)
        self.assertEqual(tool.status, Status.DOWN)


@override_settings(STORAGES=PLAIN_STATIC)
class ToolViewTests(TestCase):
    def setUp(self):
        self.tool = Tool.objects.create(name="Band saw", functional=True)

    def test_home_lists_tools_without_a_schedule(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'href="/other/band-saw"')

    def test_tool_page(self):
        response = self.client.get(self.tool.get_absolute_url())
        self.assertEqual(response.status_code, 200)

    def test_unknown_tool_is_404(self):
        response = self.client.get(reverse("tool", kwargs={"area_slug": "other", "tool_slug": "nope"}))
        self.assertEqual(response.status_code, 404)

    def test_report_problem_requires_a_description(self):
        url = reverse("report_problem", kwargs=self.tool.url_kwargs)
        response = self.client.post(url, {"latest_issue": "  "})
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "is-invalid", status_code=400)
        self.assertContains(response, "Describe the problem so the next person", status_code=400)
        self.tool.refresh_from_db()
        self.assertTrue(self.tool.functional)

    def test_report_problem_and_mark_working(self):
        report = reverse("report_problem", kwargs=self.tool.url_kwargs)
        response = self.client.post(report, {"latest_issue": "  Blade snapped  "})
        self.assertRedirects(response, "/other/band-saw")
        self.tool.refresh_from_db()
        self.assertFalse(self.tool.functional)
        self.assertEqual(self.tool.latest_issue, "Blade snapped")

        self.client.post(reverse("mark_working", kwargs=self.tool.url_kwargs))
        self.tool.refresh_from_db()
        self.assertTrue(self.tool.functional)

    def test_actions_reject_get(self):
        for name in ("report_problem", "mark_working", "log_maintenance"):
            url = reverse(name, kwargs=self.tool.url_kwargs)
            self.assertEqual(self.client.get(url).status_code, 405, name)

    @mock.patch("tools.views.timezone.localdate", return_value=TODAY)
    def test_log_maintenance(self, _):
        self.client.post(reverse("log_maintenance", kwargs=self.tool.url_kwargs))
        self.tool.refresh_from_db()
        self.assertEqual(self.tool.last_maintained, TODAY)

    def test_admin_without_slash_redirects(self):
        self.assertRedirects(
            self.client.get("/admin"), "/admin/", status_code=301, fetch_redirect_response=False
        )


@override_settings(STORAGES=PLAIN_STATIC)
class SiteNameTests(TestCase):
    def test_empty_home_page(self):
        self.assertContains(self.client.get(reverse("home")), "No tools yet")

    def test_defaults_to_tool_status(self):
        response = self.client.get(reverse("home"))
        self.assertContains(response, "<title>Tool Status</title>", html=False)

    @override_settings(SITE_NAME="Woodshop")
    def test_uses_configured_name(self):
        response = self.client.get(reverse("home"))
        self.assertContains(response, "<title>Woodshop</title>", html=False)


@override_settings(STORAGES=PLAIN_STATIC)
class AreaPermissionTests(TestCase):
    def setUp(self):
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

    def test_home_groups_tools_by_area(self):
        Tool.objects.create(name="Loose tool", functional=True)
        response = self.client.get(reverse("home"))
        self.assertContains(response, 'id="woodshop"')
        self.assertContains(response, "Metal shop")
        self.assertContains(response, "Other tools")

    def test_edit_link_only_for_area_editors(self):
        url = self.saw.get_absolute_url()
        self.client.force_login(self.editor)
        self.assertContains(self.client.get(url), "Edit in admin")
        self.client.force_login(self.group_member)
        self.assertNotContains(self.client.get(url), "Edit in admin")


class SlugTests(TestCase):
    def setUp(self):
        self.woodshop = Area.objects.create(name="Woodshop")
        self.metal = Area.objects.create(name="Metal Shop")

    def test_area_slug_is_made_from_name(self):
        self.assertEqual(self.woodshop.slug, "woodshop")
        self.assertEqual(self.metal.slug, "metal-shop")

    def test_reserved_area_slugs_are_avoided(self):
        self.assertEqual(Area.objects.create(name="Admin").slug, "admin-area")
        self.assertEqual(Area.objects.create(name="Other").slug, "other-area")

    def test_tool_slug_and_url(self):
        tool = Tool.objects.create(name="Band Saw (14\")", functional=True, area=self.woodshop)
        self.assertEqual(tool.slug, "band-saw-14")
        self.assertEqual(tool.get_absolute_url(), "/woodshop/band-saw-14")

    def test_tool_slugs_unique_within_area_only(self):
        a = Tool.objects.create(name="Grinder", functional=True, area=self.metal)
        b = Tool.objects.create(name="grinder", functional=True, area=self.metal)
        c = Tool.objects.create(name="Grinder!", functional=True, area=self.woodshop)
        self.assertEqual((a.slug, b.slug, c.slug), ("grinder", "grinder-2", "grinder"))

    def test_saving_keeps_slug(self):
        tool = Tool.objects.create(name="Lathe", functional=True, area=self.metal)
        tool.functional = False
        tool.save(update_fields=["functional"])
        tool.refresh_from_db()
        self.assertEqual(tool.slug, "lathe")

    def test_moving_area_updates_url(self):
        tool = Tool.objects.create(name="Lathe", functional=True, area=self.metal)
        tool.area = self.woodshop
        tool.save()
        self.assertEqual(tool.get_absolute_url(), "/woodshop/lathe")

    def test_renaming_area_updates_slug(self):
        self.metal.name = "Metalwork"
        self.metal.save()
        self.assertEqual(self.metal.slug, "metalwork")

    @override_settings(STORAGES=PLAIN_STATIC)
    def test_wrong_area_is_404(self):
        Tool.objects.create(name="Lathe", functional=True, area=self.metal)
        self.assertEqual(self.client.get("/woodshop/lathe").status_code, 404)
        self.assertEqual(self.client.get("/metal-shop/lathe").status_code, 200)

    def test_old_name_urls_redirect(self):
        Tool.objects.create(name="Band saw", functional=True, area=self.woodshop)
        response = self.client.get("/Band%20saw")
        self.assertRedirects(response, "/woodshop/band-saw", status_code=301, fetch_redirect_response=False)


class RenameTests(TestCase):
    def test_renaming_a_tool_keeps_one_row(self):
        tool = Tool.objects.create(name="Band saw", functional=True)
        tool.name = "Big band saw"
        tool.save()
        self.assertEqual(Tool.objects.count(), 1)
        self.assertEqual(Tool.objects.get().slug, "big-band-saw")


@override_settings(STORAGES=PLAIN_STATIC)
class AdminQueryTests(TestCase):
    """Admin list pages should make the same number of queries however many rows they show."""

    def setUp(self):
        self.client.force_login(User.objects.create_superuser("admin", password="x"))

    def add_rows(self, count):
        start = Area.objects.count()
        for i in range(start, start + count):
            Tool.objects.create(name=f"Tool {i}", area=Area.objects.create(name=f"Area {i}"))

    def queries_for(self, url):
        with CaptureQueriesContext(connection) as queries:
            self.client.get(url)
        return len(queries)

    def assert_flat(self, url):
        self.add_rows(2)
        self.client.get(url)  # warm up
        few = self.queries_for(url)
        self.add_rows(8)
        self.assertEqual(self.queries_for(url), few)

    def test_tool_list(self):
        self.assert_flat(reverse("admin:tools_tool_changelist"))

    def test_area_list(self):
        self.assert_flat(reverse("admin:tools_area_changelist"))


SSO_PROVIDERS = {
    "openid_connect": {
        "APPS": [
            {
                "provider_id": "sso",
                "name": "Authentik",
                "client_id": "test",
                "secret": "test",
                "settings": {"server_url": "https://sso.example/"},
            }
        ]
    }
}


@override_settings(OIDC_SUPERUSER_GROUP="Systems", OIDC_GROUPS_CLAIM="groups")
class SsoGroupSyncTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("sam")
        self.woodshop = Area.objects.create(name="Woodshop")

    def sso_login(self, user, extra_data):
        sociallogin = SimpleNamespace(account=SimpleNamespace(extra_data=extra_data))
        user_logged_in.send(sender=User, request=None, user=user, sociallogin=sociallogin)
        user.refresh_from_db()

    def test_groups_come_from_userinfo_then_id_token(self):
        self.sso_login(self.user, {"userinfo": {"groups": ["Members"]}, "id_token": {"groups": ["x"]}})
        self.assertEqual(list(self.user.groups.values_list("name", flat=True)), ["Members"])
        self.sso_login(self.user, {"id_token": {"groups": ["Woodshop team"]}})
        self.assertEqual(list(self.user.groups.values_list("name", flat=True)), ["Woodshop team"])

    def test_claim_can_be_a_single_string(self):
        self.assertEqual(group_names_from({"groups": " Systems "}), {"Systems"})
        self.assertEqual(group_names_from({}), set())

    def test_superuser_group_grants_and_revokes_superuser(self):
        self.sso_login(self.user, {"userinfo": {"groups": ["Systems"]}})
        self.assertTrue(self.user.is_superuser)
        self.assertTrue(self.user.is_staff)
        self.sso_login(self.user, {"userinfo": {"groups": ["Members"]}})
        self.assertFalse(self.user.is_superuser)
        self.assertFalse(self.user.is_staff)

    @override_settings(OIDC_SUPERUSER_GROUP="")
    def test_no_superuser_group_means_no_superusers(self):
        self.sso_login(self.user, {"userinfo": {"groups": ["Systems"]}})
        self.assertFalse(self.user.is_superuser)

    def test_area_editor_group_gets_staff(self):
        self.woodshop.editor_groups.add(Group.objects.create(name="Woodshop team"))
        self.sso_login(self.user, {"userinfo": {"groups": ["Woodshop team"]}})
        self.assertTrue(self.user.is_staff)
        self.assertFalse(self.user.is_superuser)

    def test_direct_area_editor_keeps_staff(self):
        self.woodshop.editors.add(self.user)
        self.sso_login(self.user, {"userinfo": {"groups": []}})
        self.assertTrue(self.user.is_staff)

    def test_password_logins_are_left_alone(self):
        admin = User.objects.create_superuser("admin", password="x")
        user_logged_in.send(sender=User, request=None, user=admin)
        admin.refresh_from_db()
        self.assertTrue(admin.is_superuser)


@override_settings(STORAGES=PLAIN_STATIC)
class SsoTemplateTests(TestCase):
    def test_no_sign_in_buttons_without_oidc(self):
        self.assertNotContains(self.client.get(reverse("home")), "Sign in")
        self.assertNotContains(self.client.get(reverse("admin:login")), "Sign in with")

    @override_settings(OIDC_ENABLED=True, OIDC_PROVIDER_NAME="Authentik", SOCIALACCOUNT_PROVIDERS=SSO_PROVIDERS)
    def test_sign_in_buttons_with_oidc(self):
        self.assertContains(self.client.get(reverse("home")), "Sign in")
        self.assertContains(self.client.get(reverse("admin:login")), "Sign in with Authentik")

    def test_sign_out_when_signed_in(self):
        self.client.force_login(User.objects.create_user("sam"))
        self.assertContains(self.client.get(reverse("home")), "Sign out")
