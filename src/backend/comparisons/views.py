from uuid import UUID

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from core.security import student_required
from core.pagination import paginate
from pilot.forms import PostingForm
from pilot.models import PostingMatch, ProgressSnapshot
from pilot.services import postings, presenter, skillprint
from reference.selectors import latest_available
from reference.models import ContentVersion
from reference.services import available_content_versions
from skills.services import list_student_skills
from .models import MatchResult
from .services import create_comparison, delete_match, get_match, list_matches


def render_compare(request, form=None):
    careers = paginate(request, latest_available("career").prefetch_related("requirements"), "careers_page")
    jobs = paginate(request, latest_available("job").prefetch_related("requirements"), "jobs_page")
    return render(request, "core/compare.html", {"active": "compare", "careers": careers, "jobs": jobs,
        "mine": paginate(request, postings.list_postings(actor=request.user).order_by("-created_at", "pk"), "postings_page"), "form": form if form is not None else PostingForm(),
        "has_skills": list_student_skills(actor=request.user).exists()})


@student_required
@require_GET
def compare(request):
    return render_compare(request)


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


def _related_notes(skill_ids):
    skill_ids = set(skill_ids)
    versions = presenter.note_versions().filter(field_note__skills__in=skill_ids).distinct()[:3]
    return [presenter.note_card(version) for version in versions]


def _reference_detail(request, result):
    groups = presenter.reference_groups(result)
    version = result.target_version
    details = getattr(version, "details", None)
    company = details.company.company_name if details and details.company else ""
    recommendation_page = paginate(request, result.recommendations.select_related("resource_version"))
    suggestions = list(recommendation_page)
    available_ids = presenter.reference_available([r.resource_version_id for r in suggestions])
    names = {str(o.skill_id): o.skill.skill_name for o in result.outcomes.all()}
    recommendations = [{"record": r, "rank": r.priority_rank, "title": r.resource_version.title, "pk": r.resource_version_id,
        "kind": r.get_resource_kind_display().lower(), "available": r.resource_version_id in available_ids,
        "skills": [names.get(row["skill_id"], "Skill") for row in r.reason.get("skills", [])]} for r in suggestions]
    levels = dict(result.inputs.values_list("skill_id", "level_used"))
    current = dict(list_student_skills(actor=request.user).values_list("skill_id", "proficiency_level"))
    rerun = available_content_versions().filter(pk=version.pk, kind__in=["career", "job"]).exists()
    summary = presenter.summary_for(
        title=version.title, subtitle=company or "Published career profile", company=company,
        location=details.location if details else "", created_at=result.created_at, score=result.score,
        mandatory_status=result.mandatory_status, reported_count=result.reported_count, relevant_count=result.relevant_count,
        is_provisional=result.is_provisional, alg_version=result.alg_version, version_label=f"reference version {version.version_no}",
        groups=groups, rerun_url=reverse("comparisons:run", args=[version.pk]) if rerun else "",
        delete_url=reverse("comparisons:delete", args=[result.pk]), private=False)
    notes = _related_notes(r["skill_id"] for g in ("gap", "unreported") for r in groups[g])
    return render(request, "core/result.html", {"active": "compare", "summary": summary, "groups": groups,
        "recommendations": recommendations, "recommendation_page": recommendation_page, "notes": notes,
        "changed_since": any(current.get(skill_id) != level for skill_id, level in levels.items())})


def _posting_detail(request, match):
    groups = presenter.posting_groups(match)
    names = {d["skill_id"]: d["name"] for d in match.detail}
    recommendation_page = paginate(request, match.recommendations)
    saved = list(recommendation_page)
    versions = ContentVersion.objects.in_bulk([r["version_id"] for r in saved])
    available = presenter.reference_available([r["version_id"] for r in saved])
    recommendations = []
    for row in saved:
        version = versions.get(UUID(row["version_id"]))
        recommendations.append({"rank": row["rank"], "title": version.title if version else "Unavailable resource",
            "pk": row["version_id"], "kind": row["kind"], "available": UUID(row["version_id"]) in available,
            "skills": [names.get(skill["skill_id"], "Skill") for skill in row["reason"]["skills"]]})
    current = {str(k): v for k, v in list_student_skills(actor=request.user).values_list("skill_id", "proficiency_level")}
    rerun = reverse("pilot:posting-run", args=[match.posting_id]) if match.posting_id else ""
    summary = presenter.summary_for(
        title=match.target_title, subtitle=match.target_company, company=match.target_company, location="",
        created_at=match.created_at, score=match.score, mandatory_status=match.mandatory_status,
        reported_count=match.reported_count, relevant_count=match.relevant_count, is_provisional=match.is_provisional,
        alg_version=match.alg_version, version_label="pasted posting", groups=groups, rerun_url=rerun,
        delete_url=reverse("comparisons:delete", args=[match.pk]), private=True)
    notes = _related_notes(UUID(r["skill_id"]) for g in ("gap", "unreported") for r in groups[g])
    return render(request, "core/result.html", {"active": "compare", "summary": summary, "groups": groups,
        "recommendations": recommendations, "recommendation_page": recommendation_page, "notes": notes,
        "changed_since": any(current.get(d["skill_id"]) != d["level_used"] for d in match.detail)})


@student_required
@require_GET
def detail(request, match_id):
    try:
        return _reference_detail(request, get_match(actor=request.user, match_id=match_id))
    except MatchResult.DoesNotExist:
        pass
    try:
        return _posting_detail(request, postings.get_posting_match(actor=request.user, match_id=match_id))
    except PostingMatch.DoesNotExist:
        raise Http404 from None


@student_required
@require_GET
def journey(request):
    student = request.student
    snapshots = ProgressSnapshot.objects.filter(student=student).order_by("-created_at", "pk")
    snapshot_page = paginate(request, snapshots, "snapshots_page")
    snaps = list(snapshot_page)
    # Include the preceding save across a page boundary when computing deltas.
    preceding = snapshots[snapshot_page.end_index():snapshot_page.end_index() + 1].first() if snaps else None
    timeline = []
    for i, snap in enumerate(snaps):
        prev = snaps[i + 1] if i + 1 < len(snaps) else preceding
        changes = []
        scoring_changed = bool(prev and snap.scoring_version != prev.scoring_version)
        if prev and not scoring_changed:
            for key, label in skillprint.CATEGORIES:
                diff = round(snap.categories.get(key, 0) - prev.categories.get(key, 0), 1)
                if diff:
                    changes.append((label, diff))
        timeline.append({"snap": snap, "changes": changes, "skill_total": len(snap.skills),
                         "scoring_changed": scoring_changed, "legacy_score": not skillprint.snapshot_is_current(snap)})
    result_page = paginate(request, list_matches(actor=request.user).annotate(met=Count("outcomes", filter=Q(outcomes__status="met")), total=Count("outcomes")).order_by("-created_at", "match_id"))
    posting_page = paginate(request, postings.list_posting_matches(actor=request.user), "posting_matches_page")
    history = []
    for m in result_page:
        history.append({"title": m.target_version.title, "created_at": m.created_at, "score": m.score, "is_provisional": m.is_provisional,
            "status": presenter.match_status(m.score, m.mandatory_status), "requirements_met": m.met, "requirements_total": m.total,
            "url": reverse("comparisons:detail", args=[m.pk]), "delete_url": reverse("comparisons:delete", args=[m.pk])})
    posting_history = []
    for m in posting_page:
        posting_history.append({"title": f"{m.target_title} — {m.target_company}", "created_at": m.created_at, "score": m.score, "is_provisional": m.is_provisional,
            "status": presenter.match_status(m.score, m.mandatory_status), "requirements_met": sum(d["status"] == "met" for d in m.detail),
            "requirements_total": len(m.detail), "url": reverse("comparisons:detail", args=[m.pk]), "delete_url": reverse("comparisons:delete", args=[m.pk])})
    oldest = snapshots.filter(scoring_version=ProgressSnapshot.CURRENT_SCORING).order_by("created_at", "pk").first()
    return render(request, "core/journey.html", {"active": "journey", "timeline": timeline,
        "results": result_page, "history": history, "posting_history": posting_history,
        "snapshot_page": snapshot_page, "posting_page": posting_page, "oldest": oldest,
        "has_legacy_snapshots": snapshots.exclude(scoring_version=ProgressSnapshot.CURRENT_SCORING).exists(),
        "radar": skillprint.radar_svg(skillprint.scores_for_student(student), oldest.categories if oldest else None)})


@student_required
@require_POST
def remove(request, match_id):
    try:
        delete_match(actor=request.user, match_id=match_id)
    except MatchResult.DoesNotExist:
        try:
            postings.delete_posting_match(actor=request.user, match_id=match_id)
        except PostingMatch.DoesNotExist:
            raise Http404 from None
    messages.success(request, "Comparison deleted.")
    return redirect("comparisons:journey")
