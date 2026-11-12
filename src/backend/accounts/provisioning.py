"""Explicit local provisioning, separate from public registration and demo data.

The bootstrap helper is trusted setup code: expose it only through the management
command. All later provisioning requires an authenticated business administrator.
"""
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction

from auditing.models import AuditEvent
from auditing.services import _record_event
from .models import Account, AccountRole, Role, Student
from .permissions import require_role_administrator
from .services import assign_role, remove_role


def normalized_email(email):
    value = Account.objects.normalize_email(email)
    validate_email(value)
    return value


def _new_account(email, password):
    email = normalized_email(email)
    if Account.objects.filter(login_email__iexact=email).exists():
        raise ValidationError("An account with this email already exists; its credentials were not changed.")
    if not isinstance(password, str) or not password:
        raise ValidationError("A password is required.")
    validate_password(password, user=Account(login_email=email))
    return Account.objects.create_user(email, password)


@transaction.atomic
def _bootstrap_administrator(*, email, password):
    # A fixed existing role row serializes competing first-administrator setups.
    role = Role.objects.select_for_update().get(role_name=Role.Name.ADMINISTRATOR)
    if AccountRole.objects.filter(role=role).exists():
        raise ValidationError("An administrator has already been provisioned, including disabled accounts. Use the existing administrator.")
    account = _new_account(email, password)
    AccountRole.objects.create(account=account, role=role)
    _record_event(event_type=AuditEvent.Type.ROLE_ASSIGNED, subject=account,
                  metadata={"role_name": role.role_name})
    return account


@transaction.atomic
def create_maintainer(*, actor, email, password):
    require_role_administrator(actor)
    account = _new_account(email, password)
    assign_role(actor=actor, account=account, role=Role.objects.get(role_name=Role.Name.MAINTAINER))
    return account


@transaction.atomic
def change_maintainer_access(*, actor, email, grant):
    require_role_administrator(actor)
    if type(grant) is not bool:
        raise ValidationError("Choose whether to grant or revoke maintainer access.")
    account = Account.objects.select_for_update().get(login_email__iexact=normalized_email(email))
    if grant and (Student.objects.filter(account=account).exists() or
                  AccountRole.objects.filter(account=account, role__role_name=Role.Name.STUDENT).exists()):
        raise ValidationError("Keep student and maintainer accounts separate. Create a new maintainer account instead.")
    role = Role.objects.get(role_name=Role.Name.MAINTAINER)
    if grant:
        assign_role(actor=actor, account=account, role=role)
    else:
        remove_role(actor=actor, account=account, role=role)
    return account
