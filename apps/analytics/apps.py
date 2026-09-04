from django.apps import AppConfig


class AnalyticsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.analytics"

    def ready(self):
        # Wires dispensing at the counter through to the data centre.
        from . import signals

        signals.connect()
