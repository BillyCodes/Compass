"""Authenticated source reuse, review previews, Field Notes and selected imports."""
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods
from accounts.permissions import require_content_editor
from pilot.services.presenter import note_card
from .curation import editorial_versions, publication_issues
from .maintenance_forms import ExistingSourceForm, FieldNoteForm
from .onet_import import import_careers, import_plan, plan_fingerprint
from .career_skills import version_suggestions
from .services import attach_source, set_field_note_profile


@never_cache
@login_required
@require_GET
def preview(request, version_id):
    require_content_editor(request.user)
    version = get_object_or_404(editorial_versions(), pk=version_id)
    associations = version_suggestions(version)
    return render(request, 'reference/maintenance/preview.html', dict(
        active='maintenance', version=version, issues=publication_issues(version), associations=associations,
        note=note_card(version) if version.kind == 'insight' else None,
        source_credits=version.source_links.all()))


def _editable(version):
    return version.status == 'draft' and version.item.retired_at is None


@never_cache
@login_required
@require_http_methods(['GET', 'POST'])
def reuse_source(request, version_id):
    require_content_editor(request.user)
    version = get_object_or_404(editorial_versions(), pk=version_id)
    if not _editable(version):
        messages.error(request, 'Only active drafts can be edited.')
        return redirect('maintenance:dashboard')
    form = ExistingSourceForm(request.POST if request.method == 'POST' else None,
                              initial={'expected_revision': version.draft_revision, 'usage': 'link'})
    if request.method == 'POST' and form.is_valid():
        try:
            values = dict(form.cleaned_data)
            source = values.pop('source')
            attach_source(actor=request.user, version_id=version.pk, source_id=source.pk, **values)
        except ValidationError as exc:
            form.add_error(None, '; '.join(exc.messages))
        else:
            messages.success(request, 'Existing source attached. Review its usage for this edition.')
            return redirect('maintenance:edit_content', version_id=version.pk)
    return render(request, 'reference/maintenance/curation_form.html', dict(active='maintenance',
        heading='Reuse an existing source', guidance='Source metadata stays shared. Usage, changes and additional credit belong to this edition.', form=form, version=version))


@never_cache
@login_required
@require_http_methods(['GET', 'POST'])
def field_note(request, version_id):
    require_content_editor(request.user)
    version = get_object_or_404(editorial_versions(), pk=version_id, kind='insight')
    if not _editable(version):
        messages.error(request, 'Only active drafts can be edited.')
        return redirect('maintenance:dashboard')
    profile = getattr(version, 'field_note', None)
    initial = {'expected_revision': version.draft_revision, 'author_name': version.original_author}
    if profile:
        initial.update({name: getattr(profile, name) for name in FieldNoteForm.base_fields if name not in ('expected_revision', 'skills')})
        initial['skills'] = profile.skills.all()
    form = FieldNoteForm(request.POST if request.method == 'POST' else None, initial=initial)
    if request.method == 'POST' and form.is_valid():
        try:
            set_field_note_profile(actor=request.user, version_id=version.pk, **form.cleaned_data)
        except ValidationError as exc:
            form.add_error(None, '; '.join(exc.messages))
        else:
            messages.success(request, 'Author details and skill tags saved.')
            return redirect('maintenance:edit_content', version_id=version.pk)
    return render(request, 'reference/maintenance/curation_form.html', dict(active='maintenance',
        heading='Field Note author and skill tags', guidance='Use accurate author details. Organization, experience, quotes, projects and tags are optional. Original notes display as personal reflections.', form=form, version=version))


class ImportForm(forms.Form):
    fingerprint = forms.CharField(min_length=64, max_length=64, widget=forms.HiddenInput())


@never_cache
@login_required
@require_http_methods(['GET', 'POST'])
def onet_import(request):
    require_content_editor(request.user)
    plan = []
    form = ImportForm(request.POST if request.method == 'POST' else None)
    try:
        plan = import_plan()
        if request.method == 'GET':
            form = ImportForm(initial={'fingerprint': plan_fingerprint(plan)})
        elif form.is_valid():
            plan = import_careers(actor=request.user, dry_run=False, expected_fingerprint=form.cleaned_data['fingerprint'])
            changed = sum(row['action'] in ('create', 'successor') for row in plan)
            messages.success(request, f'{changed} career drafts imported. Nothing was published.')
            return redirect('maintenance:dashboard')
    except ValidationError as exc:
        form.add_error(None, '; '.join(exc.messages))
    return render(request, 'reference/maintenance/onet_import.html', dict(active='maintenance', plan=plan, form=form))
