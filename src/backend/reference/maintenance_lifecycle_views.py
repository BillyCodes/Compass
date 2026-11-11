"""Confirmed maintainer actions for correcting or withdrawing published editions."""
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from accounts.permissions import require_content_editor
from .models import ContentVersion
from .services import create_successor_draft, retire_content_version


class ConfirmActionForm(forms.Form):
    pass


@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def successor(request, version_id):
    require_content_editor(request.user)
    version = get_object_or_404(ContentVersion.objects.select_related("item"), pk=version_id)
    if version.status == ContentVersion.Status.DRAFT or version.item.retired_at is not None:
        messages.error(request, "Choose a published or retired edition of an active content item.")
        return redirect("maintenance:dashboard")
    form = ConfirmActionForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        try:
            draft = create_successor_draft(actor=request.user, version_id=version.pk)
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, f"Draft version {draft.version_no} is ready to edit.")
            return redirect("maintenance:edit_content", version_id=draft.pk)
    return render(request, "reference/maintenance/lifecycle_confirm.html", {
        "active": "maintenance", "version": version, "form": form,
        "title": "Create successor draft", "button": "Open successor draft",
        "description": "Copy this edition's text, sources, details and skill mappings into a new draft. "
                       "If this item already has a draft, it will be opened instead. "
                       "Existing editions and saved comparisons stay unchanged. "
                       "The new draft becomes available to students only after publication.",
    })


@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def retire(request, version_id):
    require_content_editor(request.user)
    version = get_object_or_404(ContentVersion.objects.select_related("item"), pk=version_id)
    if version.status != ContentVersion.Status.PUBLISHED:
        messages.error(request, "Only published editions can be retired.")
        return redirect("maintenance:dashboard")
    form = ConfirmActionForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        try:
            retire_content_version(actor=request.user, version_id=version.pk)
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, "Edition retired. Saved comparisons and audit history are preserved.")
            return redirect("maintenance:dashboard")
    return render(request, "reference/maintenance/lifecycle_confirm.html", {
        "active": "maintenance", "version": version, "form": form,
        "title": "Retire edition", "button": "Confirm retirement",
        "description": "Withdraw this edition from current listings and new comparisons. "
                       "Other published editions of the same item may remain available. "
                       "Saved comparisons retain their historical data. Retirement cannot be undone; "
                       "create and publish a successor draft if the content is needed again.",
    })
