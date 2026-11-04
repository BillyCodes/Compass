from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST
from core.security import student_required
from reference.services import available_content_versions
from reference.selectors import latest_available
from skills.services import list_student_skills
from skills.models import ProficiencyLevel
from .models import MatchResult
from .services import create_comparison, delete_match, get_match, list_matches


@student_required
@require_GET
def compare(request):
    return render(request, "core/compare.html", {"active": "compare",
        "careers": latest_available("career"), "jobs": latest_available("job"),
        "has_skills": list_student_skills(actor=request.user).exists()})


@student_required
@require_POST
def run(request, version_id):
    version = get_object_or_404(available_content_versions().filter(kind__in=["career", "job"]), pk=version_id)
    try:
        result = create_comparison(actor=request.user, target_version_id=version.pk)
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
        return redirect("comparisons:compare")
    except IntegrityError as exc:
        if getattr(exc.__cause__, "sqlstate", None) != "23514":
            raise
        # A reviewed edition can be withdrawn during recommendation assembly.
        messages.error(request, "Reference content changed. Reload the targets and try again.")
        return redirect("comparisons:compare")
    return redirect("comparisons:detail", match_id=result.pk)


@student_required
@require_GET
def detail(request, match_id):
    try:
        result = get_match(actor=request.user, match_id=match_id)
    except MatchResult.DoesNotExist:
        raise Http404 from None
    levels = dict(result.inputs.values_list("skill_id", "level_used"))
    requirements = {r.skill_id: r for r in result.target_version.requirements.all()}
    labels = dict(ProficiencyLevel.choices)
    groups = {"met": [], "gap": [], "unreported": []}
    for outcome in result.outcomes.all():
        requirement = requirements[outcome.skill_id]
        level = levels[outcome.skill_id]
        groups[outcome.status].append({"name": outcome.skill.skill_name,
            "level": level, "label": "Unreported" if level is None else labels[level],
            "required_label": labels[requirement.required_level], "required_level": requirement.required_level,
            "mandatory": requirement.mandatory, "weight": requirement.weight, "gap": outcome.gap})
    for rows in groups.values():
        rows.sort(key=lambda row: (not row["mandatory"], -row["weight"], row["name"]))
    suggestions = list(result.recommendations.all())
    available_ids = set(available_content_versions().exclude(skill_mappings__skill__status="retired").filter(pk__in=[r.resource_version_id for r in suggestions]).values_list("pk", flat=True))
    names = {str(o.skill_id): o.skill.skill_name for o in result.outcomes.all()}
    recommendations = [{"record": r, "available": r.resource_version_id in available_ids,
        "skills": [names.get(row["skill_id"], "Skill") for row in r.reason.get("skills", [])]} for r in suggestions]
    current = dict(list_student_skills(actor=request.user).values_list("skill_id", "proficiency_level"))
    changed = any(current.get(skill_id) != level for skill_id, level in levels.items())
    return render(request, "core/result.html", {"active": "compare", "r": result,
        "groups": groups, "recommendations": recommendations, "changed_since": changed})


@student_required
@require_GET
def journey(request):
    return render(request, "core/journey.html", {"active": "journey", "results": list_matches(actor=request.user)})


@student_required
@require_POST
def remove(request, match_id):
    try:
        delete_match(actor=request.user, match_id=match_id)
    except MatchResult.DoesNotExist:
        raise Http404 from None
    messages.success(request, "Comparison deleted.")
    return redirect("comparisons:journey")
