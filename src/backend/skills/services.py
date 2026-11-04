"""Validated catalog edits and owner-scoped student writes."""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from accounts.models import Role, Student
from accounts.permissions import has_role, require_content_editor
from .models import Skill, StudentCourse, StudentSkill


def _owned_student(actor):
    if not has_role(actor, Role.Name.STUDENT):
        raise PermissionDenied("A student account is required.")
    student = Student.objects.filter(account=actor).first()
    if student is None:
        raise PermissionDenied("A student profile is required.")
    return student


def list_student_skills(*, actor):
    # There is no caller-supplied owner ID to trust or accidentally reuse.
    return StudentSkill.objects.filter(student=_owned_student(actor)).select_related("skill")


@transaction.atomic
def set_student_skill(*, actor, skill_id, proficiency_level, evidence_text=""):
    student = _owned_student(actor)
    # Lock the skill while checking retirement, and serialize concurrent upserts.
    skill = Skill.objects.select_for_update().get(pk=skill_id)
    if skill.status != Skill.Status.ACTIVE:
        raise ValidationError({"skill": "This skill is retired."})
    # Reject booleans/fractions rather than silently coercing them into integers.
    if type(proficiency_level) is not int or not 0 <= proficiency_level <= 5:
        raise ValidationError({"proficiency_level": "Choose an integer from 0 to 5."})
    if not isinstance(evidence_text, str):
        raise ValidationError({"evidence_text": "Evidence must be plain text."})
    record = StudentSkill.objects.filter(student=student, skill=skill).first()
    if record is None:
        record = StudentSkill(student=student, skill=skill)
    record.proficiency_level = proficiency_level
    record.evidence_text = evidence_text
    record.full_clean()
    record.save()
    return record


@transaction.atomic
def create_skill(*, actor, skill_name, category=""):
    require_content_editor(actor)
    skill = Skill(skill_name=skill_name.strip(), category=category.strip())
    skill.full_clean()
    skill.save()
    return skill


@transaction.atomic
def retire_skill(*, actor, skill_id):
    require_content_editor(actor)
    skill = Skill.objects.select_for_update().get(pk=skill_id)
    skill.status = Skill.Status.RETIRED
    skill.save(update_fields=["status"])
    return skill


@transaction.atomic
def select_student_course(*, actor, course_item_id):
    from reference.models import ContentItem, ContentKind, ContentVersion
    student = _owned_student(actor)
    item = ContentItem.objects.select_for_update().get(pk=course_item_id)
    if item.kind != ContentKind.COURSE or item.retired_at is not None:
        raise ValidationError("Choose an available course.")
    if not ContentVersion.objects.filter(item=item, status=ContentVersion.Status.PUBLISHED).exists():
        raise ValidationError("This course has no available published version.")
    record = StudentCourse.objects.filter(student=student, course_item=item).first()
    if record is None:
        record = StudentCourse(student=student, course_item=item)
        record.full_clean()
        record.save()
    return record


def list_student_courses(*, actor):
    return StudentCourse.objects.filter(student=_owned_student(actor)).select_related("course_item")


@transaction.atomic
def remove_student_course(*, actor, course_item_id):
    deleted, _ = StudentCourse.objects.filter(student=_owned_student(actor), course_item_id=course_item_id).delete()
    return bool(deleted)


@transaction.atomic
def remove_student_skill(*, actor, skill_id):
    student = _owned_student(actor)
    # Share the comparison/proficiency locking convention, including retirement.
    Skill.objects.select_for_update().get(pk=skill_id)
    deleted, _ = StudentSkill.objects.filter(student=student, skill_id=skill_id).delete()
    return bool(deleted)
