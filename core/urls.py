from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView
from allauth.account.views import LogoutView

from tools.sso import backchannel_logout

urlpatterns = [
    # Without this, /admin would match the legacy tool route and 404.
    path("admin", RedirectView.as_view(url="/admin/", permanent=True)),
    # The admin's Log out goes through allauth, so it also ends the SSO session.
    path("admin/logout/", LogoutView.as_view()),
    path("admin/", admin.site.urls),
    path("accounts/oidc/sso/backchannel-logout/", backchannel_logout, name="sso_backchannel_logout"),
    path("accounts/", include("allauth.urls")),
    path("", include("tools.urls")),
]
