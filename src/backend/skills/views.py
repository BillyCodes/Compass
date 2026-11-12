from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from core.security import student_required
from core.pagination import paginate
from pilot.services import skillprint as sp
from reference.models import ContentSkill, ContentVersion
from reference.selectors import latest_available
from reference.services import available_content_versions
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
    skill_page = paginate(request, list_student_skills(actor=request.user).order_by("skill__category", "skill__skill_name", "skill_id"), "skills_page")
    records = list(skill_page)
    by_category = {}
    for record in records:
        record.from_resume = record.evidence_text.startswith("Resume:")
        by_category.setdefault(sp.category_key(record.skill.category) or "other", []).append(record)
    scores = sp.scores_for_student(request.student)
    groups = [(key, label, scores[key], by_category.get(key, [])) for key, label in sp.CATEGORIES]
    if by_category.get("other"):
        groups.append(("other", "Other", None, by_category["other"]))
    last_snap = sp.last_snapshot(request.student)
    comparable_snap = last_snap if sp.snapshot_is_current(last_snap) else None
    course_page = paginate(request, list_student_courses(actor=request.user).order_by("-selected_at", "pk"), "courses_page")
    selections = list(course_page)
    item_ids = [s.course_item_id for s in selections]
    latest = {v.item_id: v for v in latest_available("course").filter(item_id__in=item_ids)}
    # Keep an unavailable selection readable as history without offering it as
    # currently available. Prefer an eligible edition whenever one exists.
    historical = (ContentVersion.objects.filter(item_id__in=set(item_ids) - latest.keys(),
                  status__in=["published", "retired"]).select_related("details")
                  .order_by("item_id", "-version_no").distinct("item_id"))
    fallback = {v.item_id: v for v in historical}
    courses = [{"selection": s, "version": latest.get(s.course_item_id) or fallback.get(s.course_item_id),
                "available": s.course_item_id in latest} for s in selections]
    return render(request, "core/skillprint.html", {"active": "skillprint", "form": form,
        "course_form": CourseForm(prefix="course"), "groups": groups, "levels": ProficiencyLevel.choices, "courses": courses,
        "radar": sp.radar_svg(scores, comparable_snap.categories if comparable_snap else None), "last_snap": comparable_snap,
        "legacy_snapshot": bool(last_snap and not comparable_snap),
        "skill_page": skill_page, "course_page": course_page})


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
    active = Skill.objects.filter(status="active")
    categories = [(c, sp.CATEGORY_LABELS.get(sp.category_key(c), c))
                  for c in active.exclude(category="").values_list("category", flat=True).order_by("category").distinct()]
    job_versions = available_content_versions(kind="job").values("pk")
    catalog = (active.select_related("detail")
               .annotate(postings=Count("content_requirements", filter=Q(content_requirements__version__in=job_versions), distinct=True)))
    if category:
        catalog = catalog.filter(category=category)
    if query:
        catalog = catalog.filter(Q(skill_name__icontains=query) | Q(category__icontains=query)
                                 | Q(detail__description__icontains=query) | Q(detail__aliases__icontains=query))
    skill_page = paginate(request, catalog.order_by("skill_name", "skill_id"))
    skills = list(skill_page)
    course_versions = latest_available("course").values("pk")
    codes = {}
    for skill_id, code in (ContentSkill.objects.filter(version_id__in=course_versions, skill_id__in=[s.pk for s in skills])
                           .exclude(version__details__course_code="").values_list("skill_id", "version__details__course_code")):
        codes.setdefault(skill_id, []).append(code)
    for skill in skills:
        skill.course_codes = sorted(codes.get(skill.pk, []))
    mine = dict(list_student_skills(actor=request.user).filter(skill_id__in=[s.pk for s in skills]).values_list("skill_id", "proficiency_level"))
    return render(request, "core/explorer.html", {"active": "explorer", "skills": skill_page,
        "categories": categories, "current": category, "query": query, "mine": mine})
