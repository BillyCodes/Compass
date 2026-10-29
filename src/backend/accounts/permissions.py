"""Business roles and ownership are enforced separately from Django admin flags."""
from django.core.exceptions import PermissionDenied

from .models import Role


def has_role(account, role_name):
    return bool(account.is_authenticated and account.is_active and
                account.role_assignments.filter(role__role_name=role_name).exists())


def require_role_administrator(account):
    # A Compass role does not grant is_staff/is_superuser, or vice versa.
    if not has_role(account, Role.Name.ADMINISTRATOR):
        raise PermissionDenied("Role administration is restricted.")
