"""Maintainer actions for publishing draft content."""

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from accounts.permissions import require_content_editor

from .models import ContentVersion
from .services import publish_content_version


class PublishContentForm(forms.Form):
    expected_revision = forms.IntegerField(
        min_value=1,
        widget=forms.HiddenInput(),
    )


@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def publish_content(request, version_id):
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
            "Only drafts belonging to active content items can be published.",
        )
        return redirect("maintenance:dashboard")

    if request.method == "POST":
        form = PublishContentForm(request.POST)

        if form.is_valid():
            try:
                publish_content_version(
                    actor=request.user,
                    version_id=version.pk,
                    expected_revision=form.cleaned_data[
                        "expected_revision"
                    ],
                )

            except ValidationError as exc:
                form.add_error(None, "; ".join(exc.messages))

            else:
                messages.success(
                    request,
                    "Content published successfully.",
                )
                return redirect("maintenance:dashboard")

    else:
        form = PublishContentForm(
            initial={
                "expected_revision": version.draft_revision,
            }
        )

    return render(
        request,
        "reference/maintenance/publish_confirm.html",
        {
            "active": "maintenance",
            "version": version,
            "form": form,
        },
    )