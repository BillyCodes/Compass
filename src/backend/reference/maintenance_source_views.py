"""Maintainer actions for removing sources from draft content."""

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from accounts.permissions import require_content_editor

from .models import ContentSource, ContentVersion
from .services import detach_source

from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from .maintenance_forms import EditSourceForm
from .services import edit_draft_source

class RemoveSourceForm(forms.Form):
    expected_revision = forms.IntegerField(
        min_value=1,
        widget=forms.HiddenInput,
    )


@never_cache
@login_required
@require_POST
def remove_source(request, version_id, source_id):
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
            "Sources can only be removed from drafts of active content items.",
        )
        return redirect("maintenance:dashboard")

    get_object_or_404(
        ContentSource,
        version=version,
        source_id=source_id,
    )

    form = RemoveSourceForm(request.POST)

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
        removed = detach_source(
            actor=request.user,
            version_id=version.pk,
            source_id=source_id,
            expected_revision=form.cleaned_data["expected_revision"],
        )
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    else:
        if removed:
            messages.success(
                request,
                "Source removed from this draft successfully.",
            )
        else:
            messages.info(
                request,
                "This source was already removed from the draft.",
            )

    return redirect(
        "maintenance:edit_content",
        version_id=version.pk,
    )

@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def edit_source(request, version_id, source_id):
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
            "Sources can only be edited in drafts of active content items.",
        )
        return redirect("maintenance:dashboard")

    link = get_object_or_404(
        ContentSource.objects.select_related("source"),
        version=version,
        source_id=source_id,
    )

    if request.method == "POST":
        form = EditSourceForm(request.POST)

        if form.is_valid():
            try:
                edit_draft_source(
                    actor=request.user,
                    version_id=version.pk,
                    source_id=link.source_id,
                    expected_revision=form.cleaned_data[
                        "expected_revision"
                    ],
                    source_title=form.cleaned_data["source_title"],
                    source_url_or_identifier=form.cleaned_data[
                        "source_url_or_identifier"
                    ],
                )

            except ValidationError as exc:
                form.add_error(None, "; ".join(exc.messages))

            else:
                messages.success(
                    request,
                    "Source updated for this draft successfully.",
                )
                return redirect(
                    "maintenance:edit_content",
                    version_id=version.pk,
                )

    else:
        form = EditSourceForm(
            initial={
                "source_title": link.source.source_title,
                "source_url_or_identifier": (
                    link.source.source_url_or_identifier
                ),
                "expected_revision": version.draft_revision,
            }
        )

    return render(
        request,
        "reference/maintenance/source_edit_form.html",
        {
            "active": "maintenance",
            "form": form,
            "version": version,
        },
    )