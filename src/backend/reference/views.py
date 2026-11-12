import uuid

from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET
from core.security import student_required
from core.pagination import paginate
from pilot.services import presenter
from skills.models import Skill
from skills.services import list_student_skills
from .selectors import available_learning_versions, latest_available
from .services import available_content_versions


@student_required
@require_GET
def field_notes(request):
    try:
        skill_id = uuid.UUID(request.GET.get("skill", ""))
    except ValueError:
        skill_id = None
    available_ids = latest_available("insight").values("pk")
    versions = presenter.note_versions(skill_id=skill_id)
    notes = paginate(request, versions)
    cards = [presenter.note_card(version) for version in notes]
    tagged = Skill.objects.filter(field_notes__version_id__in=available_ids).distinct().order_by("skill_name")
    return render(request, "core/field_notes.html", {"active": "notes", "notes": notes, "cards": cards, "tagged": tagged,
                  "current": str(skill_id) if skill_id else "", "has_sample": any(n["is_sample"] for n in cards)})


@student_required
@require_GET
def field_note_detail(request, version_id):
    version = get_object_or_404(available_content_versions(kind="insight").select_related("field_note"), pk=version_id)
    mine = dict(list_student_skills(actor=request.user).values_list("skill_id", "proficiency_level"))
    more = [presenter.note_card(v) for v in presenter.note_versions().exclude(pk=version.pk)[:3]]
    return render(request, "core/field_note_detail.html", {"active": "notes", "note": presenter.note_card(version), "mine": mine, "more": more,
                  "source_credits": version.source_links.select_related("source")})


@student_required
@require_GET
def learning_detail(request, version_id):
    version = get_object_or_404(available_learning_versions(), pk=version_id)
    details = getattr(version, "details", None)
    url = details.resource_url if details else ""
    if not url.lower().startswith(("https://", "http://")):
        url = ""
    return render(request, "core/learning_detail.html", {"active": "compare", "version": version, "details": details, "resource_url": url,
                  "source_credits": version.source_links.select_related("source")})
