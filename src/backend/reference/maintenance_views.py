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
    AddSourceForm, MITResourceForm,
    CreateContentForm,
    EditContentForm,
)
from .curation import PROVIDER_PRESETS, PROVIDER_GUIDANCE, editorial_versions, publication_issues
from .models import ContentVersion, ContentKind, ReferenceSource
from .services import (
    attach_source,
    create_content_item,
    create_draft_version,
    create_reference_source,
    update_draft_version, set_content_details,
)


@never_cache
@login_required
@require_GET
def dashboard(request):
    require_content_editor(request.user)

    versions = editorial_versions()

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

    filters = {key: request.GET.get(key, "").strip() for key in ("q", "kind", "origin", "status", "provider", "missing")}
    if filters["q"]:
        versions = versions.filter(Q(title__icontains=filters["q"]) | Q(body__icontains=filters["q"]) | Q(source_links__source__external_id__icontains=filters["q"]))
    for field in ("kind", "origin", "status"):
        if filters[field]:
            versions = versions.filter(**{field: filters[field]})
    if filters["provider"]:
        versions = versions.filter(source_links__source__provider=filters["provider"])
    versions = versions.distinct()
    if filters["missing"] == "yes":
        # This curated catalog is deliberately small. Reuse the exact diagnostics
        # so the filter and preview agree, retaining SQL pagination afterwards.
        ids = [v.pk for v in versions.filter(status="draft") if publication_issues(v)]
        versions = versions.filter(pk__in=ids)
    query = request.GET.copy()
    query.pop("page", None)

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
            "filters": filters, "kinds": ContentKind.choices, "origins": ContentVersion.Origin.choices,
            "statuses": ContentVersion.Status.choices, "providers": ReferenceSource._meta.get_field("provider").choices,
            "filter_query": query.urlencode(),
            "page": page,
        },
    )


@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def create_content(request):
    require_content_editor(request.user)

    preset = request.GET.get("preset", "")
    initial = {"reflection": {"kind": "insight", "origin": "original"},
               "mit": {"kind": "resource", "origin": "external"},
               "bls": {"kind": "career", "origin": "external"}}.get(preset, {})
    form_class = MITResourceForm if preset == "mit" else CreateContentForm
    form = form_class(request.POST if request.method == "POST" else None, initial=initial)

    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                item = create_content_item(
                    actor=request.user,
                    kind=form.cleaned_data["kind"],
                )

                version = create_draft_version(
                    actor=request.user,
                    item_id=item.pk,
                    title=form.cleaned_data["title"],
                    body=form.cleaned_data["body"],
                    origin=form.cleaned_data["origin"] or ContentVersion.Origin.EXTERNAL,
                    original_author=form.cleaned_data["original_author"],
                    originality_confirmed=form.cleaned_data["originality_confirmed"],
                )

                if preset == "mit":
                    url = form.cleaned_data["resource_url"]
                    edition = form.cleaned_data["edition"]
                    prerequisites = form.cleaned_data["prerequisites"]
                    version = update_draft_version(actor=request.user, version_id=version.pk,
                        expected_revision=version.draft_revision, title=version.title,
                        body=f"{version.body}\n\nEdition: {edition}\nPrerequisites / placement: {prerequisites}\nExternal learning resource; no MIT enrollment, academic credit or certification is implied.")
                    set_content_details(actor=request.user, version_id=version.pk,
                        expected_revision=version.draft_revision, provider="MIT OpenCourseWare", resource_url=url)
                    version.refresh_from_db()
                    source = create_reference_source(actor=request.user, source_title=version.title,
                        source_url_or_identifier=url, source_url=url, provider="mit", publisher="MIT OpenCourseWare",
                        source_version=edition, raw_metadata={"prerequisites": prerequisites})
                    attach_source(actor=request.user, version_id=version.pk, source_id=source.pk,
                        expected_revision=version.draft_revision, usage="link")

        except ValidationError as exc:
            form.add_error(None, "; ".join(exc.messages))

        else:
            messages.success(
                request,
                "Draft created successfully.",
            )
            return redirect("maintenance:edit_content", version_id=version.pk)

    return render(
        request,
        "reference/maintenance/content_form.html",
        {
            "active": "maintenance",
            "form": form,
            "is_edit": False,
            "guidance": PROVIDER_GUIDANCE.get(preset, "Write an original personal reflection with an accurate author name; no invented external source is needed." if preset == "reflection" else ""),
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
                    origin=form.cleaned_data["origin"] or version.origin,
                    original_author=form.cleaned_data["original_author"],
                    originality_confirmed=form.cleaned_data["originality_confirmed"],
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
                "origin": version.origin,
                "original_author": version.original_author,
                "originality_confirmed": version.originality_confirmed,
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
                        **form.source_metadata(),
                        source_title=form.cleaned_data["source_title"],
                        source_url_or_identifier=form.cleaned_data[
                            "source_url_or_identifier"
                        ],
                    )

                    attach_source(
                        actor=request.user,
                        **form.source_usage(),
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
        initial = {"expected_revision": version.draft_revision,
                   **PROVIDER_PRESETS.get(request.GET.get("provider"), {})}
        if request.GET.get("provider") == "bls":
            from .onet_import import CAREERS
            code = version.source_links.filter(source__provider="onet").values_list("source__external_id", flat=True).first()
            if code in CAREERS:
                title, path = CAREERS[code]
                url = f"https://www.bls.gov/ooh/{path}.htm"
                initial.update(source_title=f"BLS Occupational Outlook Handbook — {title}", source_url=url,
                    source_url_or_identifier=url, external_id=code, usage="link",
                    attribution_text="U.S. Bureau of Labor Statistics, Occupational Outlook Handbook.",
                    raw_metadata={"soc_code": code, "review_note": "Record wage year, geography and projection period before including figures."})
        form = AddSourceForm(initial=initial)

    return render(
        request,
        "reference/maintenance/source_form.html",
        {"guidance": PROVIDER_GUIDANCE.get(request.GET.get("provider"), "Select a provider preset or reuse an existing source. Review the actual material and its usage terms."),
            "active": "maintenance",
            "form": form,
            "version": version,
        },
    )
