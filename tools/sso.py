"""Keeps SSO users' groups and admin rights in step with the identity provider.

On every SSO login:
- the user's Django groups are set to exactly the groups in the OIDC groups
  claim, creating any that don't exist yet (so groups are managed in the
  identity provider, not the Django admin);
- they're a superuser only while they're in OIDC_SUPERUSER_GROUP;
- they get staff status (needed to open the admin) while they're a superuser
  or an editor of any area, directly or through one of those groups.

Users who log in with a password, such as a break-glass admin, are untouched.
"""

from allauth.account.signals import user_logged_in
from django.conf import settings
from django.contrib.auth.models import Group
from django.db import transaction
from django.db.models import Q
from django.dispatch import receiver

from .models import Area


def claims_from(extra_data):
    """The user's claims: allauth stores userinfo and/or the ID token."""
    return extra_data.get("userinfo") or extra_data.get("id_token") or {}


def group_names_from(claims):
    value = claims.get(settings.OIDC_GROUPS_CLAIM) or []
    if isinstance(value, str):
        value = [value]
    return {str(name).strip() for name in value if str(name).strip()}


@transaction.atomic
def sync_user(user, group_names):
    groups = [Group.objects.get_or_create(name=name)[0] for name in sorted(group_names)]
    user.groups.set(groups)

    superuser_group = settings.OIDC_SUPERUSER_GROUP
    user.is_superuser = bool(superuser_group) and superuser_group in group_names
    edits_an_area = Area.objects.filter(Q(editors=user) | Q(editor_groups__in=groups)).exists()
    user.is_staff = user.is_superuser or edits_an_area
    user.save(update_fields=["is_superuser", "is_staff"])


@receiver(user_logged_in)
def sync_on_sso_login(sender, request, user, **kwargs):
    sociallogin = kwargs.get("sociallogin")
    if sociallogin is None:
        return
    sync_user(user, group_names_from(claims_from(sociallogin.account.extra_data)))
