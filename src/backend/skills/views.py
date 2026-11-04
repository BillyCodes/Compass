from itertools import groupby
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from core.security import student_required
from reference.models import ContentVersion
from .forms import CourseForm, LevelForm, SkillForm
from .models import ProficiencyLevel, Skill
from .services import (list_student_courses, list_student_skills, remove_student_course,
                       remove_student_skill, select_student_course, set_student_skill)


@student_required
@require_http_methods(["GET", "POST"])
def skillprint(request):
    form = SkillForm(request.POST if request.method == "POST" else None, prefix="skill")
    if request.method == "POST" and form.is_valid():
        try:
            set_student_skill(actor=request.user, skill_id=form.cleaned_data["skill"].pk,
                              proficiency_level=form.cleaned_data["level"], evidence_text=form.cleaned_data["evidence"])
        except ValidationError as exc:
            form.add_error(None, exc.messages)
        else:
            messages.success(request, "Skill saved.")
            return redirect("skills:skillprint")
    records = list(list_student_skills(actor=request.user).order_by("skill__category", "skill__skill_name"))
    groups = [(category or "Other", list(items)) for category, items in groupby(records, key=lambda r: r.skill.category)]
    selections = list(list_student_courses(actor=request.user))
    editions = ContentVersion.objects.filter(item_id__in=[s.course_item_id for s in selections], status__in=["published", "retired"]).order_by("item_id", "-version_no")
    latest = {}
    for version in editions:
        latest.setdefault(version.item_id, version)
    courses = [{"selection": s, "version": latest.get(s.course_item_id)} for s in selections]
    return render(request, "core/skillprint.html", {"active": "skillprint", "form": form,
        "course_form": CourseForm(prefix="course"), "groups": groups, "levels": ProficiencyLevel.choices, "courses": courses})


@student_required
@require_POST
def update_skill(request, skill_id):
    record = get_object_or_404(list_student_skills(actor=request.user), skill_id=skill_id)
    form = LevelForm(request.POST)
    if form.is_valid():
        try:
            set_student_skill(actor=request.user, skill_id=skill_id, proficiency_level=form.cleaned_data["level"], evidence_text=record.evidence_text)
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        else:
            messages.success(request, "Proficiency updated.")
    else:
        messages.error(request, "Choose a proficiency level from 0 to 5.")
    return redirect("skills:skillprint")


@student_required
@require_POST
def remove_skill(request, skill_id):
    get_object_or_404(list_student_skills(actor=request.user), skill_id=skill_id)
    remove_student_skill(actor=request.user, skill_id=skill_id)
    messages.success(request, "Skill removed. Previous comparison snapshots are preserved.")
    return redirect("skills:skillprint")


@student_required
@require_POST
def add_course(request):
    form = CourseForm(request.POST, prefix="course")
    if form.is_valid():
        try:
            select_student_course(actor=request.user, course_item_id=form.cleaned_data["course"].item_id)
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        else:
            messages.success(request, "Course selected. Your proficiency levels have not changed.")
    else:
        messages.error(request, "Choose an available published course.")
    return redirect("skills:skillprint")


@student_required
@require_POST
def remove_course(request, item_id):
    get_object_or_404(list_student_courses(actor=request.user), course_item_id=item_id)
    remove_student_course(actor=request.user, course_item_id=item_id)
    messages.success(request, "Course selection removed.")
    return redirect("skills:skillprint")


@student_required
@require_GET
def explorer(request):
    query = request.GET.get("q", "").strip()[:100]
    category = request.GET.get("category", "").strip()[:100]
    catalog = Skill.objects.filter(status="active")
    categories = list(catalog.exclude(category="").values_list("category", flat=True).order_by("category").distinct())
    if category:
        catalog = catalog.filter(category=category)
    if query:
        catalog = catalog.filter(Q(skill_name__icontains=query) | Q(category__icontains=query))
    mine = dict(list_student_skills(actor=request.user).values_list("skill_id", "proficiency_level"))
    return render(request, "core/explorer.html", {"active": "explorer", "skills": catalog,
        "categories": categories, "current": category, "query": query, "mine": mine})
