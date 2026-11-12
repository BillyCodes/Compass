"""Provider guidance and read-only publication diagnostics for editors."""
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import ContentVersion

PROVIDER_PRESETS = {
    'onet': dict(provider='onet', publisher='U.S. Department of Labor, Employment and Training Administration',
                 license_name='CC BY 4.0', license_url='https://creativecommons.org/licenses/by/4.0/', source_version='31.0'),
    'bls': dict(provider='bls', publisher='U.S. Bureau of Labor Statistics',
                license_name='Public domain (BLS text)', license_url='https://www.bls.gov/ooh/about/OOH-FAQs.htm'),
    'mit': dict(provider='mit', publisher='MIT OpenCourseWare', usage='link'),
}
PROVIDER_GUIDANCE = {
    'onet': 'Preserve the O*NET-SOC code, dataset edition and exact file checksum. Credit USDOL/ETA and link CC BY 4.0. Describe Compass changes; software examples do not establish proficiency requirements or endorsement.',
    'bls': 'Cite the exact BLS profile. For wage/outlook text, record the wage year, geography, SOC code and projection period in raw metadata. Use occupation-specific figures on combined pages. Check separate rights for third-party images.',
    'mit': 'Start with a link to the archived MIT OpenCourseWare edition. Record the edition and prerequisites in the description. Linking does not award MIT credit or certification. Before copying/adapting, check the resource notices, instructor credits and applicable CC BY-NC-SA terms.',
}


def publication_issues(version):
    """Actionable diagnostics; PostgreSQL remains the authoritative publication guard."""
    issues = []
    if version.status != 'draft':
        return []
    if version.item.retired_at:
        issues.append('This content item is retired.')
    if not version.title.strip() or not version.body.strip():
        issues.append('Enter a title and description.')
    if version.origin == 'legacy':
        issues.append('Classify the content origin.')
    if version.origin == 'original' and (not version.original_author.strip() or not version.originality_confirmed):
        issues.append('Enter the original author and confirm originality and cited borrowed material.')
    links = list(version.source_links.all())
    if not links and version.origin != 'original':
        issues.append('Attach at least one reference source.')
    for link in links:
        source = link.source
        try:
            source.full_clean()
            link.full_clean(exclude=['version', 'source'])
        except ValidationError as exc:
            issues.extend(f'{source.source_title}: {message}' for message in exc.messages)
        if version.origin not in ('external', 'original'):
            continue
        missing = []
        if source.provider == 'unknown':
            missing.append('provider')
        for field in ('publisher', 'source_url'):
            if not getattr(source, field).strip():
                missing.append(field.replace('_', ' '))
        if link.usage == 'unknown':
            missing.append('source usage')
        if link.usage != 'link':
            for field in ('license_name', 'license_url', 'attribution_text'):
                if not getattr(source, field).strip():
                    missing.append(field.replace('_', ' '))
        if link.usage in ('adapted', 'interpretation') and not link.changes.strip():
            missing.append('changes / interpretation notes')
        if source.provider == 'onet':
            for field in ('source_version', 'external_id', 'file_sha256'):
                if not getattr(source, field).strip():
                    missing.append(field.replace('_', ' '))
        if missing:
            issues.append(f'{source.source_title}: complete {", ".join(missing)}.')
    requirements = list(version.requirements.all())
    mappings = list(version.skill_mappings.all())
    if any(row.skill.status != 'active' for row in requirements + mappings):
        issues.append('Replace retired skills in requirements or coverage.')
    if version.kind in ('career', 'job') and not any(row.required_level > 0 and row.weight > 0 for row in requirements):
        issues.append('Add a reviewed skill requirement with a positive level and weight. Levels, weights and mandatory flags are Compass editorial decisions.')
    if version.kind in ('course', 'resource') and not any(row.coverage_level > 0 for row in mappings):
        issues.append('Add at least one reviewed positive skill coverage mapping.')
    details = getattr(version, 'details', None)
    if details:
        try:
            details.full_clean()
        except ValidationError as exc:
            issues.extend(exc.messages)
        if details.expires_at and details.expires_at <= timezone.now():
            issues.append('Update the expired content details.')
    if version.kind == 'resource' and (not details or not details.resource_url):
        issues.append('Enter the learning resource URL in resource details.')
    if version.kind == 'course' and (not details or not (details.course_code.strip() or details.provider.strip())):
        issues.append('Enter a course code or provider in course details.')
    return issues


def editorial_versions():
    return ContentVersion.objects.select_related('item', 'details', 'field_note').prefetch_related(
        'source_links__source', 'requirements__skill', 'skill_mappings__skill', 'field_note__skills')
