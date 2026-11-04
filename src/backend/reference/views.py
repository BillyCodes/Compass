from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET
from core.security import student_required
from .selectors import latest_available
from .services import available_content_versions


@student_required
@require_GET
def field_notes(request):
    return render(request, "core/field_notes.html", {"active": "notes", "notes": latest_available("insight")})


@student_required
@require_GET
def field_note_detail(request, version_id):
    version = get_object_or_404(available_content_versions(kind="insight"), pk=version_id)
    return render(request, "core/field_note_detail.html", {"active": "notes", "version": version})


@student_required
@require_GET
def learning_detail(request, version_id):
    version = get_object_or_404(available_content_versions().filter(kind__in=["course", "resource"]).exclude(skill_mappings__skill__status="retired"), pk=version_id)
    details = getattr(version, "details", None)
    url = details.resource_url if details else ""
    if not url.lower().startswith(("https://", "http://")):
        url = ""
    return render(request, "core/learning_detail.html", {"active": "compare", "version": version, "details": details, "resource_url": url})
