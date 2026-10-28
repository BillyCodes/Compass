from django.apps import AppConfig


class CoreConfig(AppConfig):
    """Register public-page functionality and shared site assets with Django."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
