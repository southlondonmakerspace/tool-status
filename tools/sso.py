"""Keeps SSO users' groups and admin rights in step with the identity provider.

On every SSO login:
- the user's Django groups are set to exactly the groups in the OIDC groups
  claim, creating any that don't exist yet (so groups are managed in the
  identity provider, not the Django admin);
- they're a superuser only while they're in OIDC_SUPERUSER_GROUP;
- they get staff status (needed to open the admin) while they're a superuser,
  an editor of any area (directly or through one of those groups), or in a
  group that has been given permissions in the admin.

Users who log in with a password, such as a break-glass admin, are untouched.

Logging out works both ways:
- signing out here also ends the provider session (RP-initiated logout), by
  redirecting to the provider's end_session_endpoint;
- the provider can end sessions here through back-channel logout, by POSTing
  a signed logout token to /accounts/oidc/sso/backchannel-logout/.
"""

import logging
from datetime import timedelta
from importlib import import_module
from urllib.parse import urlencode

import jwt
import requests
from allauth.account.adapter import DefaultAccountAdapter
from allauth.account.signals import user_logged_in
from allauth.socialaccount.models import SocialAccount
from allauth.socialaccount.providers.openid_connect.views import OpenIDConnectOAuth2Adapter
from django.conf import settings
from django.contrib.auth.models import Group, Permission
from django.contrib.auth.signals import user_logged_out
from django.db import transaction
from django.db.models import Q
from django.dispatch import receiver
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import Area, SsoSession

log = logging.getLogger(__name__)

BACKCHANNEL_LOGOUT_EVENT = "http://schemas.openid.net/event/backchannel-logout"
# Set in the session on SSO login, so signing out knows to end the provider session too.
SSO_SESSION_FLAG = "tools_sso_login"


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
    has_group_permissions = Permission.objects.filter(group__in=groups).exists()
    user.is_staff = user.is_superuser or edits_an_area or has_group_permissions
    user.save(update_fields=["is_superuser", "is_staff"])


@receiver(user_logged_in)
def sync_on_sso_login(sender, request, user, **kwargs):
    sociallogin = kwargs.get("sociallogin")
    if sociallogin is None:
        return
    sync_user(user, group_names_from(claims_from(sociallogin.account.extra_data)))
    record_session(request, user, sociallogin.account.extra_data.get("id_token") or {})


def record_session(request, user, id_token):
    """Remember which Django session this SSO login started."""
    if request is None:
        return
    request.session[SSO_SESSION_FLAG] = True
    if request.session.session_key is None:
        request.session.save()
    # Drop records of sessions that have expired by now.
    expired = timezone.now() - timedelta(seconds=settings.SESSION_COOKIE_AGE)
    SsoSession.objects.filter(created__lt=expired).delete()
    SsoSession.objects.update_or_create(
        session_key=request.session.session_key,
        defaults={"user": user, "sid": str(id_token.get("sid") or "")},
    )


@receiver(user_logged_out)
def forget_session(sender, request, user, **kwargs):
    if request is not None and request.session.session_key:
        SsoSession.objects.filter(session_key=request.session.session_key).delete()


def session_store_class():
    return import_module(settings.SESSION_ENGINE).SessionStore


def end_sessions(sessions):
    """Ends the given SSO sessions. Returns how many there were."""
    store = session_store_class()
    keys = list(sessions.values_list("session_key", flat=True))
    for key in keys:
        store(session_key=key).delete()
    sessions.delete()
    return len(keys)


def openid_config(request):
    return OpenIDConnectOAuth2Adapter(request, settings.OIDC_PROVIDER_ID).openid_config


class LogoutTokenError(Exception):
    pass


def decode_logout_token(request, token):
    """Validates a back-channel logout token as the OIDC spec requires."""
    config = openid_config(request)
    client_id = settings.SOCIALACCOUNT_PROVIDERS["openid_connect"]["APPS"][0]["client_id"]
    try:
        key = jwt.PyJWKClient(config["jwks_uri"]).get_signing_key_from_jwt(token).key
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256", "RS384", "RS512", "ES256", "ES384", "ES512"],
            audience=client_id,
            issuer=config["issuer"],
            options={"require": ["iat", "iss", "aud"]},
        )
    except jwt.PyJWTError as e:
        raise LogoutTokenError(f"invalid token: {e}") from e
    if BACKCHANNEL_LOGOUT_EVENT not in (claims.get("events") or {}):
        raise LogoutTokenError("not a back-channel logout token")
    if "nonce" in claims:
        raise LogoutTokenError("logout tokens must not have a nonce")
    if not claims.get("sub") and not claims.get("sid"):
        raise LogoutTokenError("no sub or sid")
    return claims


def sessions_for(claims):
    """The SSO sessions a logout token refers to: by sid if given, else every
    session of the user it names."""
    sessions = SsoSession.objects.all()
    if claims.get("sub"):
        account = SocialAccount.objects.filter(
            provider=settings.OIDC_PROVIDER_ID, uid=str(claims["sub"])
        ).first()
        if account is None:
            return sessions.none()
        sessions = sessions.filter(user_id=account.user_id)
    if claims.get("sid"):
        sessions = sessions.filter(sid=str(claims["sid"]))
    return sessions


@csrf_exempt
@require_POST
@never_cache
def backchannel_logout(request):
    if not settings.OIDC_ENABLED:
        return JsonResponse({"error": "invalid_request"}, status=400)
    token = request.POST.get("logout_token", "")
    try:
        claims = decode_logout_token(request, token)
    except (LogoutTokenError, requests.RequestException) as e:
        log.warning("Rejected back-channel logout: %s", e)
        return JsonResponse({"error": "invalid_request"}, status=400)
    ended = end_sessions(sessions_for(claims))
    log.info("Back-channel logout ended %d session(s)", ended)
    return HttpResponse(status=200)


class AccountAdapter(DefaultAccountAdapter):
    """Signing out after an SSO login also signs out of the provider."""

    def get_logout_redirect_url(self, request):
        # allauth asks for this before logging out, so the session is still there.
        url = super().get_logout_redirect_url(request)
        if not (settings.OIDC_ENABLED and request.session.get(SSO_SESSION_FLAG)):
            return url
        try:
            end_session = openid_config(request).get("end_session_endpoint")
        except requests.RequestException:
            log.warning("Couldn't reach the provider to end its session")
            return url
        if not end_session:
            return url
        client_id = settings.SOCIALACCOUNT_PROVIDERS["openid_connect"]["APPS"][0]["client_id"]
        query = urlencode({"client_id": client_id, "post_logout_redirect_uri": request.build_absolute_uri(url)})
        return f"{end_session}?{query}"
