"""Maintainer actions for career and job skill requirements."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from accounts.permissions import require_content_editor

from .maintenance_forms import ContentRequirementForm
from .models import ContentKind, ContentVersion
from .services import set_requirement

from django import forms
from django.views.decorators.http import require_POST

from .models import ContentRequirement
from .services import remove_requirement as remove_requirement_service

@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def add_requirement(request, version_id):
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
            "Requirements can only be changed in drafts of active content items.",
        )
        return redirect("maintenance:dashboard")

    if version.kind not in (ContentKind.CAREER, ContentKind.JOB):
        messages.error(
            request,
            "Only career profiles and jobs have skill requirements.",
        )
        return redirect(
            "maintenance:edit_content",
            version_id=version.pk,
        )

    if request.method == "POST":
        form = ContentRequirementForm(request.POST)

        if form.is_valid():
            try:
                set_requirement(
                    actor=request.user,
                    version_id=version.pk,
                    skill_id=form.cleaned_data["skill"].pk,
                    required_level=form.cleaned_data["required_level"],
                    mandatory=form.cleaned_data["mandatory"],
                    weight=form.cleaned_data["weight"],
                    expected_revision=form.cleaned_data[
                        "expected_revision"
                    ],
                )

            except ValidationError as exc:
                form.add_error(None, "; ".join(exc.messages))

            else:
                messages.success(
                    request,
                    "Skill requirement saved successfully.",
                )
                return redirect(
                    "maintenance:edit_content",
                    version_id=version.pk,
                )

    else:
        form = ContentRequirementForm(
            initial={
                "expected_revision": version.draft_revision,
            }
        )

    return render(
        request,
        "reference/maintenance/requirement_form.html",
        {
            "active": "maintenance",
            "form": form,
            "version": version,
        },
    )

class RemoveRequirementForm(forms.Form):
    expected_revision = forms.IntegerField(
        min_value=1,
        widget=forms.HiddenInput(),
    )


@never_cache
@login_required
@require_POST
def remove_requirement(request, version_id, skill_id):
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
            "Requirements can only be removed from drafts of active content items.",
        )
        return redirect("maintenance:dashboard")

    if version.kind not in (ContentKind.CAREER, ContentKind.JOB):
        messages.error(
            request,
            "Only career profiles and jobs have skill requirements.",
        )
        return redirect(
            "maintenance:edit_content",
            version_id=version.pk,
        )

    get_object_or_404(
        ContentRequirement,
        version=version,
        skill_id=skill_id,
    )

    form = RemoveRequirementForm(request.POST)

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
        removed = remove_requirement_service(
            actor=request.user,
            version_id=version.pk,
            skill_id=skill_id,
            expected_revision=form.cleaned_data["expected_revision"],
        )

    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))

    else:
        if removed:
            messages.success(
                request,
                "Skill requirement removed from this draft successfully.",
            )
        else:
            messages.info(
                request,
                "This requirement was already removed from the draft.",
            )

    return redirect(
        "maintenance:edit_content",
        version_id=version.pk,
    )