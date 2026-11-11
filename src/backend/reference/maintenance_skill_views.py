"""Maintainer actions for course and resource skill mappings."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import (
    require_http_methods,
    require_POST,
)

from accounts.permissions import require_content_editor

from .maintenance_forms import (
    ContentSkillForm,
    RemoveSkillMappingForm,
)
from .models import ContentKind, ContentSkill, ContentVersion
from .services import (
    remove_skill_mapping as remove_skill_mapping_service,
    set_skill_mapping,
)


@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def add_skill_mapping(request, version_id):
    require_content_editor(request.user)

    version = get_object_or_404(
        ContentVersion.objects.select_related("item"),
        pk=version_id,
    )

    if (
        version.status != ContentVersion.Status.DRAFT
        or version.item.retired_at is not None
    ):
        messages.error(
            request,
            "Skills can only be changed in drafts of active content items.",
        )
        return redirect("maintenance:dashboard")

    if version.kind not in (
        ContentKind.COURSE,
        ContentKind.RESOURCE,
    ):
        messages.error(
            request,
            "Only courses and learning resources have skill mappings.",
        )
        return redirect(
            "maintenance:edit_content",
            version_id=version.pk,
        )

    form = ContentSkillForm(
        request.POST if request.method == "POST" else None,
        initial={
            "expected_revision": version.draft_revision,
        },
    )

    if request.method == "POST" and form.is_valid():
        try:
            set_skill_mapping(
                actor=request.user,
                version_id=version.pk,
                skill_id=form.cleaned_data["skill"].pk,
                coverage_level=form.cleaned_data["coverage_level"],
                expected_revision=form.cleaned_data[
                    "expected_revision"
                ],
            )

        except ValidationError as exc:
            form.add_error(None, "; ".join(exc.messages))

        else:
            messages.success(
                request,
                "Skill coverage saved successfully.",
            )
            return redirect(
                "maintenance:edit_content",
                version_id=version.pk,
            )

    return render(
        request,
        "reference/maintenance/skill_mapping_form.html",
        {
            "active": "maintenance",
            "form": form,
            "version": version,
        },
    )


@never_cache
@login_required
@require_POST
def remove_skill_mapping(request, version_id, skill_id):
    require_content_editor(request.user)

    version = get_object_or_404(
        ContentVersion.objects.select_related("item"),
        pk=version_id,
    )

    if (
        version.status != ContentVersion.Status.DRAFT
        or version.item.retired_at is not None
    ):
        messages.error(
            request,
            "Skills can only be removed from drafts of active content items.",
        )
        return redirect("maintenance:dashboard")

    if version.kind not in (
        ContentKind.COURSE,
        ContentKind.RESOURCE,
    ):
        messages.error(
            request,
            "Only courses and learning resources have skill mappings.",
        )
        return redirect(
            "maintenance:edit_content",
            version_id=version.pk,
        )

    get_object_or_404(
        ContentSkill,
        version=version,
        skill_id=skill_id,
    )

    form = RemoveSkillMappingForm(request.POST)

    if not form.is_valid():
        messages.error(
            request,
            "The draft revision is missing or invalid. Reload and try again.",
        )
        return redirect(
            "maintenance:edit_content",
            version_id=version.pk,
        )

    try:
        removed = remove_skill_mapping_service(
            actor=request.user,
            version_id=version.pk,
            skill_id=skill_id,
            expected_revision=form.cleaned_data[
                "expected_revision"
            ],
        )

    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))

    else:
        if removed:
            messages.success(
                request,
                "Skill mapping removed from this draft successfully.",
            )
        else:
            messages.info(
                request,
                "This skill mapping was already removed from the draft.",
            )

    return redirect(
        "maintenance:edit_content",
        version_id=version.pk,
    )