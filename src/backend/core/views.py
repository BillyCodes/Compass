"""Public landing page and owner-scoped dashboard; domain writes live in feature apps."""
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET
from comparisons.services import list_matches
from reference.selectors import latest_available
from skills.services import list_student_courses, list_student_skills
from .security import student_required


@require_GET
def home(request):
    return render(request, "core/home.html", {"notes": latest_available("insight")[:3]})


@student_required
@require_GET
def onboarding(request):
    return render(request, "core/onboarding.html", {"active": "dashboard"})


@student_required
@require_GET
def dashboard(request):
    records = list(list_student_skills(actor=request.user).order_by("-proficiency_level", "skill__skill_name"))
    matches = list_matches(actor=request.user)
    return render(request, "core/dashboard.html", {
        "active": "dashboard", "today": timezone.localdate(), "top_skills": records[:5],
        "skill_count": len(records), "course_count": list_student_courses(actor=request.user).count(),
        "match_count": matches.count(), "latest": matches.first(),
        "jobs": latest_available("job")[:3], "notes": latest_available("insight")[:2],
    })
