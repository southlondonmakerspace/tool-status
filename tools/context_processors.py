from django.conf import settings


def site(request):
    return {
        "site_name": settings.SITE_NAME,
        "oidc_enabled": settings.OIDC_ENABLED,
        "oidc_provider_name": settings.OIDC_PROVIDER_NAME,
    }
