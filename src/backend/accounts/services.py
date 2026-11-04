"""Transactional operations keep profiles and role assignments consistent."""
from django.core.exceptions import ValidationError
from django.db import transaction

from auditing.models import AuditEvent
from auditing.services import _record_event

from .models import Account, AccountRole, Role, Student
from .permissions import require_role_administrator


@transaction.atomic
def create_student(*, email, password, display_name, **profile_fields):
    # Account/profile/initial role are atomic; public forms validate credentials first.
    account = Account.objects.create_user(email, password)
    student = Student.objects.create(account=account, display_name=display_name, **profile_fields)
    role = Role.objects.get(role_name=Role.Name.STUDENT)
    AccountRole.objects.create(account=account, role=role)
    _record_event(event_type=AuditEvent.Type.ROLE_ASSIGNED, subject=account, metadata={"role_name": role.role_name})
    return student


@transaction.atomic
def assign_role(*, actor, account, role):
    require_role_administrator(actor)
    account = Account.objects.select_for_update().get(pk=account.pk)
    assignment, created = AccountRole.objects.get_or_create(
        account=account, role=role, defaults={"assigned_by": actor},
    )
    if created:
        _record_event(event_type=AuditEvent.Type.ROLE_ASSIGNED, actor=actor, subject=account, metadata={"role_name": role.role_name})
    return assignment


@transaction.atomic
def remove_role(*, actor, account, role):
    require_role_administrator(actor)
    account = Account.objects.select_for_update().get(pk=account.pk)
    deleted, _ = AccountRole.objects.filter(account=account, role=role).delete()
    if deleted:
        _record_event(event_type=AuditEvent.Type.ROLE_REMOVED, actor=actor, subject=account, metadata={"role_name": role.role_name})
    return bool(deleted)


@transaction.atomic
def set_account_active(*, actor, account, is_active):
    require_role_administrator(actor)
    if type(is_active) is not bool:
        raise ValidationError({"is_active": "Use a boolean activation status."})
    account = Account.objects.select_for_update().get(pk=account.pk)
    if account.is_active != is_active:
        account.is_active = is_active
        account.save(update_fields=["is_active", "updated_at"])
        _record_event(event_type=AuditEvent.Type.ACCOUNT_ACTIVATED if is_active else AuditEvent.Type.ACCOUNT_DISABLED,
                      actor=actor, subject=account)
    return account


@transaction.atomic
def update_student_profile(*, actor, display_name, major, career_interests, graduation_year):
    from skills.services import _owned_student
    owned = _owned_student(actor)
    student = Student.objects.select_for_update().get(pk=owned.pk)
    student.display_name = display_name
    student.major = major
    student.career_interests = career_interests
    student.graduation_year = graduation_year
    student.full_clean()
    student.save(update_fields=["display_name", "major", "career_interests", "graduation_year", "updated_at"])
    return student
