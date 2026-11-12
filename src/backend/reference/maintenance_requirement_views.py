"""Maintainer actions for career and job skill requirements."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from accounts.permissions import require_content_editor

from .maintenance_forms import ContentRequirementForm
from .models import ContentKind, ContentVersion
from .services import set_requirement
from .career_skills import version_suggestions
from skills.models import Skill

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

    query = request.GET.get('q', '').strip()
    demand_only = request.GET.get('demand') == 'yes'
    show_all = request.GET.get('catalog') == 'all'
    suggestions = version_suggestions(version) if version.kind == ContentKind.CAREER else []
    active = Skill.objects.filter(status=Skill.Status.ACTIVE).order_by('skill_name')
    by_name = {skill.skill_name.casefold(): skill for skill in active}
    for row in suggestions:
        row['record'] = by_name.get(row['skill'].casefold())
    suggestions = [row for row in suggestions if row['record'] is not None]
    visible = [row for row in suggestions if (not demand_only or row['demand'])
               and (not query or query.casefold() in (row['skill'] + ' ' + row['raw_name']).casefold())]
    if suggestions and not show_all:
        choices = active.filter(pk__in=[row['record'].pk for row in visible])
    else:
        choices = active.filter(Q(skill_name__icontains=query) | Q(pk__in=[row['record'].pk for row in visible])) if query else active
        if demand_only:
            choices = choices.filter(pk__in=[row['record'].pk for row in visible])

    if request.method == "POST":
        form = ContentRequirementForm(request.POST, skills=choices)

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
        form = ContentRequirementForm(skills=choices, initial={
            "expected_revision": version.draft_revision, "skill": request.GET.get('skill', '')})

    return render(
        request,
        "reference/maintenance/requirement_form.html",
        {
            "active": "maintenance",
            "form": form,
            "version": version, "suggestions": visible, "has_suggestions": bool(suggestions),
            "query": query, "demand_only": demand_only, "show_all": show_all,
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