"""Public landing page and owner-scoped dashboard; domain writes live in feature apps."""
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET

from comparisons.models import MatchResult
from comparisons.services import list_matches
from pilot.services import presenter, skillprint
from skills.services import list_student_courses, list_student_skills
from .security import student_required

EXAMPLE_SCORES = {"programming": 80, "data": 66, "systems": 58, "security": 40, "professional": 72, "cloud": 46}


@require_GET
def home(request):
    return render(request, "core/home.html", {"notes": presenter.available_notes()[:3], "radar": skillprint.radar_svg(EXAMPLE_SCORES)})


@student_required
@require_GET
def onboarding(request):
    return render(request, "core/onboarding.html", {"active": "dashboard"})


def _greeting():
    hour = timezone.localtime().hour
    return "Good morning" if hour < 12 else ("Good afternoon" if hour < 17 else "Good evening")


@student_required
@require_GET
def dashboard(request):
    student = request.student
    records = list(list_student_skills(actor=request.user).select_related("skill").order_by("-proficiency_level", "skill__skill_name"))
    levels = {r.skill_id: r.proficiency_level for r in records}
    scores = skillprint.scores_for_student(student)
    last_snap = skillprint.last_snapshot(student)

    result = skillprint.latest_readiness(student)
    latest, groups, delta_score = None, {"met": [], "gap": [], "unreported": []}, None
    if result is not None:
        groups = presenter.reference_groups(result)
        latest = {"pk": result.pk, "title": result.target_version.title, "score": result.score, "is_provisional": result.is_provisional,
                  "status": presenter.match_status(result.score, result.mandatory_status), **presenter.counts(groups)}
        previous = (MatchResult.objects.filter(student=student, finalized=True, target_version__item_id=result.target_version.item_id)
                    .exclude(pk=result.pk).order_by("-created_at").first())
        delta_score = (result.score - previous.score) if previous else None

    matches = presenter.live_job_matches(levels)
    gap_ids = {row["skill_id"] for g in ("gap", "unreported") for row in groups[g]}
    notes = presenter.available_notes()
    notes.sort(key=lambda n: not (gap_ids and gap_ids & {s.pk for s in n["skills"]}))  # stable: tagged-for-your-gaps first
    return render(request, "core/dashboard.html", {
        "active": "dashboard", "greeting": _greeting(), "today": timezone.localdate(),
        "radar": skillprint.radar_svg(scores, last_snap.categories if last_snap else None),
        "has_prev_shape": bool(last_snap), "scores": scores, "top_skills": records[:5], "skill_count": len(records),
        "latest": latest, "readiness_delta": delta_score, "delta": skillprint.snapshot_delta(student),
        "course_count": list_student_courses(actor=request.user).count(), "matches": matches,
        "strong_count": sum(m["status"] == "Strong Match" for m in matches),
        "mission": presenter.next_mission(has_skills=bool(records), latest=latest, groups=groups), "notes": notes[:2],
    })
