from django.apps import AppConfig


class AccountsConfig(AppConfig):
    """Register the app that will own account identity and authentication."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'accounts'
