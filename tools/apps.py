from django.apps import AppConfig


class ToolsConfig(AppConfig):
    name = "tools"

    def ready(self):
        from . import sso  # noqa: F401  (connects the login signal)
