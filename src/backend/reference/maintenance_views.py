from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods

from accounts.permissions import require_content_editor

from .maintenance_forms import (
    AddSourceForm,
    CreateContentForm,
    EditContentForm,
)
from .models import ContentVersion
from .services import (
    attach_source,
    create_content_item,
    create_draft_version,
    create_reference_source,
    update_draft_version,
)


@never_cache
@login_required
@require_GET
def dashboard(request):
    require_content_editor(request.user)

    versions = ContentVersion.objects.select_related("item")

    totals = versions.aggregate(
        drafts=Count(
            "pk",
            filter=Q(status=ContentVersion.Status.DRAFT),
        ),
        published=Count(
            "pk",
            filter=Q(status=ContentVersion.Status.PUBLISHED),
        ),
        retired=Count(
            "pk",
            filter=Q(status=ContentVersion.Status.RETIRED),
        ),
    )

    page = Paginator(
        versions.order_by("title", "item_id", "-version_no"),
        20,
    ).get_page(request.GET.get("page"))

    return render(
        request,
        "reference/maintenance/dashboard.html",
        {
            "active": "maintenance",
            "totals": totals,
            "page": page,
        },
    )


@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def create_content(request):
    require_content_editor(request.user)

    form = CreateContentForm(
        request.POST if request.method == "POST" else None
    )

    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                item = create_content_item(
                    actor=request.user,
                    kind=form.cleaned_data["kind"],
                )

                create_draft_version(
                    actor=request.user,
                    item_id=item.pk,
                    title=form.cleaned_data["title"],
                    body=form.cleaned_data["body"],
                )

        except ValidationError as exc:
            form.add_error(None, "; ".join(exc.messages))

        else:
            messages.success(
                request,
                "Draft created successfully.",
            )
            return redirect("maintenance:dashboard")

    return render(
        request,
        "reference/maintenance/content_form.html",
        {
            "active": "maintenance",
            "form": form,
            "is_edit": False,
        },
    )


@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def edit_content(request, version_id):
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
            "Only drafts belonging to active content items can be edited.",
        )
        return redirect("maintenance:dashboard")

    if request.method == "POST":
        form = EditContentForm(request.POST)

        if form.is_valid():
            try:
                update_draft_version(
                    actor=request.user,
                    version_id=version.pk,
                    expected_revision=form.cleaned_data[
                        "expected_revision"
                    ],
                    title=form.cleaned_data["title"],
                    body=form.cleaned_data["body"],
                )

            except ValidationError as exc:
                form.add_error(None, "; ".join(exc.messages))

            else:
                messages.success(
                    request,
                    "Draft updated successfully.",
                )
                return redirect("maintenance:dashboard")

    else:
        form = EditContentForm(
            initial={
                "title": version.title,
                "body": version.body,
                "expected_revision": version.draft_revision,
            }
        )

    sources = version.source_links.select_related("source").order_by(
        "source__source_title",
        "pk",
    )

    return render(
        request,
        "reference/maintenance/content_form.html",
        {
            "active": "maintenance",
            "form": form,
            "version": version,
            "is_edit": True,
            "sources": sources,
        },
    )


@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def add_source(request, version_id):
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
            "Sources can only be added to drafts of active content items.",
        )
        return redirect("maintenance:dashboard")

    if request.method == "POST":
        form = AddSourceForm(request.POST)

        if form.is_valid():
            try:
                with transaction.atomic():
                    source = create_reference_source(
                        actor=request.user,
                        source_title=form.cleaned_data["source_title"],
                        source_url_or_identifier=form.cleaned_data[
                            "source_url_or_identifier"
                        ],
                    )

                    attach_source(
                        actor=request.user,
                        version_id=version.pk,
                        source_id=source.pk,
                        expected_revision=form.cleaned_data[
                            "expected_revision"
                        ],
                    )

            except ValidationError as exc:
                form.add_error(None, "; ".join(exc.messages))

            else:
                messages.success(
                    request,
                    "Source added successfully.",
                )
                return redirect(
                    "maintenance:edit_content",
                    version_id=version.pk,
                )

    else:
        form = AddSourceForm(
            initial={
                "expected_revision": version.draft_revision,
            }
        )

    return render(
        request,
        "reference/maintenance/source_form.html",
        {
            "active": "maintenance",
            "form": form,
            "version": version,
        },
    )