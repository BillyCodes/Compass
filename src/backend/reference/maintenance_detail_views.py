"""Maintainer actions for content details and reference companies."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from django.utils import timezone

from accounts.permissions import require_content_editor

from .maintenance_forms import CompanyForm, JobDetailsForm
from .models import ContentDetails, ContentKind, ContentVersion
from .services import create_company, set_content_details



@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def add_company(request, version_id):
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
            "Companies can only be created through drafts of active content items.",
        )
        return redirect("maintenance:dashboard")

    if version.kind != ContentKind.JOB:
        messages.error(
            request,
            "Company details are only available for jobs.",
        )
        return redirect(
            "maintenance:edit_content",
            version_id=version.pk,
        )

    form = CompanyForm(
        request.POST if request.method == "POST" else None
    )

    if request.method == "POST" and form.is_valid():
        try:
            create_company(
                actor=request.user,
                company_name=form.cleaned_data["company_name"],
                industry=form.cleaned_data["industry"],
            )

        except ValidationError as exc:
            form.add_error(None, "; ".join(exc.messages))

        else:
            messages.success(
                request,
                "Company created. It is now available in the company catalog.",
            )
            return redirect(
                "maintenance:edit_content",
                version_id=version.pk,
            )

    return render(
        request,
        "reference/maintenance/company_form.html",
        {
            "active": "maintenance",
            "form": form,
            "version": version,
        },
    )

@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def edit_job_details(request, version_id):
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
            "Only drafts of active content items can be edited.",
        )
        return redirect("maintenance:dashboard")

    if version.kind != ContentKind.JOB:
        messages.error(
            request,
            "Job details are only available for jobs.",
        )
        return redirect(
            "maintenance:edit_content",
            version_id=version.pk,
        )

    details = ContentDetails.objects.filter(
        version=version,
    ).first()

    initial = {
        "expected_revision": version.draft_revision,
    }

    if details is not None:
        initial.update(
            {
                "company": details.company_id,
                "location": details.location,
                "expires_at": details.expires_at,
            }
        )

    form = JobDetailsForm(
        request.POST if request.method == "POST" else None,
        initial=initial,
    )

    if request.method == "POST" and form.is_valid():
        company = form.cleaned_data["company"]

        try:
            set_content_details(
                actor=request.user,
                version_id=version.pk,
                expected_revision=form.cleaned_data[
                    "expected_revision"
                ],
                company_id=company.pk if company is not None else None,
                location=form.cleaned_data["location"],
                expires_at=form.cleaned_data["expires_at"],
            )

        except ValidationError as exc:
            form.add_error(None, "; ".join(exc.messages))

        else:
            messages.success(
                request,
                "Job details saved.",
            )
            return redirect(
                "maintenance:edit_content",
                version_id=version.pk,
            )

    return render(
        request,
        "reference/maintenance/job_details_form.html",
        {
            "active": "maintenance",
            "form": form,
            "version": version,
            "current_time_zone": (
                timezone.get_current_timezone_name()
            ),
        },
    )

@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def edit_job_details(request, version_id):
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
            "Only drafts of active content items can be edited.",
        )
        return redirect("maintenance:dashboard")

    if version.kind != ContentKind.JOB:
        messages.error(
            request,
            "Job details are only available for jobs.",
        )
        return redirect(
            "maintenance:edit_content",
            version_id=version.pk,
        )

    details = ContentDetails.objects.filter(
        version=version,
    ).first()

    initial = {
        "expected_revision": version.draft_revision,
    }

    if details is not None:
        initial.update(
            {
                "company": details.company_id,
                "location": details.location,
                "expires_at": details.expires_at,
            }
        )

    form = JobDetailsForm(
        request.POST if request.method == "POST" else None,
        initial=initial,
    )

    if request.method == "POST" and form.is_valid():
        company = form.cleaned_data["company"]

        try:
            set_content_details(
                actor=request.user,
                version_id=version.pk,
                expected_revision=form.cleaned_data[
                    "expected_revision"
                ],
                company_id=(
                    company.pk if company is not None else None
                ),
                location=form.cleaned_data["location"],
                expires_at=form.cleaned_data["expires_at"],
            )

        except ValidationError as exc:
            form.add_error(None, "; ".join(exc.messages))

        else:
            messages.success(
                request,
                "Job details saved.",
            )
            return redirect(
                "maintenance:edit_content",
                version_id=version.pk,
            )

    return render(
        request,
        "reference/maintenance/job_details_form.html",
        {
            "active": "maintenance",
            "form": form,
            "version": version,
            "current_time_zone": (
                timezone.get_current_timezone_name()
            ),
        },
    )