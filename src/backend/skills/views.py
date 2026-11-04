"""Authenticated, owner-scoped student skill and course pages."""

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import OuterRef, Subquery
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from reference.models import ContentItem, ContentKind, ContentVersion

from .forms import StudentCourseForm, StudentSkillForm
from .models import Skill
from .services import (
    list_student_courses,
    list_student_skills,
    remove_student_course,
    select_student_course,
    set_student_skill,
)


@login_required(login_url="accounts:login")
@require_http_methods(["GET", "POST"])
def student_skills(request):
    records = list_student_skills(actor=request.user)

    if request.method == "POST":
        form = StudentSkillForm(request.POST)

        if form.is_valid():
            try:
                set_student_skill(
                    actor=request.user,
                    skill_id=form.cleaned_data["skill"].pk,
                    proficiency_level=form.cleaned_data["proficiency_level"],
                    evidence_text=form.cleaned_data["evidence_text"],
                )
            except Skill.DoesNotExist:
                form.add_error(
                    "skill",
                    "This skill is no longer available.",
                )
            except ValidationError as exc:
                if hasattr(exc, "error_dict"):
                    for field, errors in exc.error_dict.items():
                        target = field if field in form.fields else None
                        for error in errors:
                            form.add_error(target, error)
                else:
                    form.add_error(None, exc)
            else:
                return redirect("skills:student-skills")
    else:
        form = StudentSkillForm()

    return render(
        request,
        "skills/student_skills.html",
        {
            "form": form,
            "records": records,
        },
    )


@login_required(login_url="accounts:login")
@require_http_methods(["GET", "POST"])
def student_courses(request):
    records = list_student_courses(actor=request.user)

    if request.method == "POST":
        form = StudentCourseForm(request.POST)

        if form.is_valid():
            try:
                select_student_course(
                    actor=request.user,
                    course_item_id=form.cleaned_data["course_item"].pk,
                )
            except ContentItem.DoesNotExist:
                form.add_error(
                    "course_item",
                    "This course is no longer available.",
                )
            except ValidationError as exc:
                for message in exc.messages:
                    form.add_error(None, message)
            else:
                return redirect("skills:student-courses")
    else:
        form = StudentCourseForm()

    published_versions = ContentVersion.objects.filter(
        item_id=OuterRef("course_item_id"),
        kind=ContentKind.COURSE,
        status=ContentVersion.Status.PUBLISHED,
    ).order_by("-version_no")

    records = records.annotate(
        selection_title=Subquery(
            published_versions.values("title")[:1]
        ),
    ).order_by("-selected_at", "selection_id")

    return render(
        request,
        "skills/student_courses.html",
        {
            "form": form,
            "records": records,
            "has_available_courses": (
                form.fields["course_item"].queryset.exists()
            ),
        },
    )


@login_required(login_url="accounts:login")
@require_POST
def student_course_remove(request, course_item_id):
    remove_student_course(
        actor=request.user,
        course_item_id=course_item_id,
    )
    return redirect("skills:student-courses")