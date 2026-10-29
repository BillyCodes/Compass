"""Transactional operations keep profiles and role assignments consistent."""
from django.db import transaction

from .models import Account, AccountRole, Role, Student
from .permissions import require_role_administrator


@transaction.atomic
def create_student(*, email, password, display_name, **profile_fields):
    # Trusted setup service, not a public registration endpoint.
    account = Account.objects.create_user(email, password)
    student = Student.objects.create(account=account, display_name=display_name, **profile_fields)
    role = Role.objects.get(role_name=Role.Name.STUDENT)
    AccountRole.objects.create(account=account, role=role)
    return student


@transaction.atomic
def assign_role(*, actor, account, role):
    require_role_administrator(actor)
    assignment, _ = AccountRole.objects.get_or_create(
        account=account, role=role, defaults={"assigned_by": actor},
    )
    return assignment
