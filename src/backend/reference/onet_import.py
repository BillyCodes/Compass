"""Small, local-file-only O*NET import. No publication or inferred scoring values."""
import csv
import hashlib
import io
import json
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import connection, transaction

from accounts.permissions import require_content_editor
from skills.models import Skill
from .career_skills import selected_examples, selection
from .models import ContentSource, ContentVersion, ContentItem, OnetCareerIdentity
from .services import (attach_source, create_content_item, create_draft_version,
                       create_reference_source, create_successor_draft, detach_source, update_draft_version)

CAREERS = {
    '15-1252.00': ('Software Developers', 'computer-and-information-technology/software-developers'),
    '15-1212.00': ('Information Security Analysts', 'computer-and-information-technology/information-security-analysts'),
    '15-2051.00': ('Data Scientists', 'math/data-scientists'),
    '15-1211.00': ('Computer Systems Analysts', 'computer-and-information-technology/computer-systems-analysts'),
    '15-1243.00': ('Database Architects', 'computer-and-information-technology/database-administrators'),
}
IMPORTER = 'compass_onet_v1'
ATTRIBUTION = ('Career descriptions and software examples originate in the O*NET® 31.0 Database, '
               'U.S. Department of Labor, Employment and Training Administration (USDOL/ETA), under CC BY 4.0. '
               'O*NET® is a trademark of USDOL/ETA. Compass selects occupations and software examples and '
               'consolidates selected names. These changes have not been approved, endorsed or tested by USDOL/ETA.')
CHANGES = ('Compass selected five computing occupations and career-specific software examples. '
           'The occupation description is reproduced unchanged. SQL consolidates the source label '
           '“Structured query language SQL”; other name normalizations are recorded in source metadata. Categories are Compass-authored. No proficiency levels, '
           'weights, mandatory requirements or learning coverage are derived from software associations.')


def _read(path, required):
    try:
        raw = path.read_bytes()
        reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
        if not required.issubset(reader.fieldnames or []):
            raise ValidationError(f'{path.name}: missing required CSV columns.')
        rows = list(reader)
        if any(None in row or any(row.get(k) is None or not row[k].strip() for k in required) for row in rows):
            raise ValidationError(f'{path.name}: malformed or empty required CSV values.')
        return rows, hashlib.sha256(raw).hexdigest()
    except (OSError, UnicodeError, csv.Error) as exc:
        raise ValidationError(f'Cannot read {path.name}: {exc}') from exc


def import_plan(directory=None, *, lock=False):
    directory = Path(directory or settings.REPOSITORY_ROOT / 'data/reference/onet/31.0')
    occupations, occupation_hash = _read(directory / 'occupation_data.csv', {'O*NET-SOC Code', 'Title', 'Description'})
    software, software_hash = _read(directory / 'software_skills.csv', {'O*NET-SOC Code', 'Title', 'Workplace Example', 'Element ID', 'Element Name', 'Hot Technology', 'In Demand'})
    plan = []
    for code, (title, bls_path) in CAREERS.items():
        matches = [row for row in occupations if row['O*NET-SOC Code'] == code]
        if len(matches) != 1 or matches[0]['Title'] != title:
            raise ValidationError(f'{code}: expected one occupation with title {title}.')
        examples = [row for row in software if row['O*NET-SOC Code'] == code]
        if not examples or any(row['Title'] != title or row['Hot Technology'] not in ('Y', 'N') or row['In Demand'] not in ('Y', 'N') for row in examples):
            raise ValidationError(f'{code}: missing or inconsistent software examples.')
        fingerprint = hashlib.sha256(json.dumps([IMPORTER, occupation_hash, software_hash, matches[0], examples], sort_keys=True).encode()).hexdigest()
        links = ContentSource.objects.filter(source__provider='onet', source__external_id=code,
            source__raw_metadata__importer=IMPORTER, version__kind='career').select_related('version__item', 'source')
        identity = OnetCareerIdentity.objects.filter(occupation_code=code).first()
        latest = None
        if identity:
            if lock:
                # Manual successor creation uses the same parent lock. Inspect
                # the latest edition only after acquiring it, so an editor's
                # concurrently created draft can never be overwritten.
                ContentItem.objects.select_for_update().get(pk=identity.item_id)
            latest = ContentVersion.objects.filter(item_id=identity.item_id).order_by('-version_no').first()
        action = 'create'
        if latest:
            if latest.item.retired_at:
                action = 'retired'
            elif any(link.version_id == latest.pk and link.source.raw_metadata.get('fingerprint') == fingerprint for link in links):
                action = 'unchanged'
            elif latest.status == 'draft':
                action = 'conflict'
            else:
                action = 'successor'
        plan.append(dict(code=code, title=title, occupation=matches[0], examples=examples,
                         occupation_hash=occupation_hash, software_hash=software_hash, fingerprint=fingerprint,
                         skills=sorted(row['skill'] for row in selected_examples(code, examples)),
                         bls_url=f'https://www.bls.gov/ooh/{bls_path}.htm', latest=latest, action=action))
    return plan


def plan_fingerprint(plan):
    return hashlib.sha256(json.dumps([(row['fingerprint'], selection(row['code'])) for row in plan], sort_keys=True).encode()).hexdigest()


@transaction.atomic
def import_careers(*, actor, dry_run=True, directory=None, expected_fingerprint=None):
    require_content_editor(actor)
    if not dry_run:
        # Serialize import identity allocation even before a content item exists.
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_advisory_xact_lock(%s)', [1946103101])
    plan = import_plan(directory, lock=not dry_run)
    if expected_fingerprint and expected_fingerprint != plan_fingerprint(plan):
        raise ValidationError('The source files changed. Reload the dry-run preview before importing.')
    if any(row['action'] == 'conflict' for row in plan):
        raise ValidationError('Changed source files conflict with an existing draft. Review that draft before importing a new edition.')
    if dry_run:
        return plan
    for row in plan:
        if row['action'] != 'retired':
            # Catalog-only enrichment also runs for unchanged editions. Never
            # rewrite their bodies, requirements, source snapshots or revisions.
            for entry in selected_examples(row['code'], row['examples']):
                name, category = entry['skill'], entry['category']
                existing = list(Skill.objects.filter(skill_name__iexact=name))
                if len(existing) > 1 or any(skill.status != 'active' for skill in existing):
                    raise ValidationError(f'Review the existing {name} skill before importing.')
                if not existing:
                    Skill.objects.create(skill_name=name, category=category)
        if row['action'] in ('unchanged', 'retired'):
            continue
        if row['action'] == 'successor':
            version = create_successor_draft(actor=actor, version_id=row['latest'].pk)
            version = update_draft_version(actor=actor, version_id=version.pk, expected_revision=version.draft_revision,
                title=row['title'], body=row['occupation']['Description'], origin='external')
            for link in list(version.source_links.filter(source__provider='onet', source__raw_metadata__importer=IMPORTER)):
                detach_source(actor=actor, version_id=version.pk, source_id=link.source_id, expected_revision=version.draft_revision)
                version.refresh_from_db()
        else:
            item = create_content_item(actor=actor, kind='career')
            OnetCareerIdentity.objects.create(occupation_code=row['code'], item=item)
            version = create_draft_version(actor=actor, item_id=item.pk, title=row['title'],
                                           body=row['occupation']['Description'], origin='external')
        for filename, checksum, raw_values in (
            ('occupation_data.csv', row['occupation_hash'], {'occupation': row['occupation']}),
            ('software_skills.csv', row['software_hash'], {'software_examples': row['examples'], 'normalizations': selection(row['code'])}),
        ):
            url = f'https://www.onetcenter.org/dl_files/database/db_31_0_csv/{filename}'
            source = create_reference_source(actor=actor, source_title=f'O*NET® 31.0 — {row["title"]} — {filename}',
                source_url_or_identifier=url, provider='onet', publisher='U.S. Department of Labor, Employment and Training Administration',
                source_url=url, source_version='31.0', external_id=row['code'], file_sha256=checksum,
                license_name='CC BY 4.0', license_url='https://creativecommons.org/licenses/by/4.0/', attribution_text=ATTRIBUTION,
                raw_metadata=dict(importer=IMPORTER, fingerprint=row['fingerprint'], local_ingestion=True, **raw_values))
            attach_source(actor=actor, version_id=version.pk, source_id=source.pk, expected_revision=version.draft_revision,
                          usage='excerpt' if filename == 'occupation_data.csv' else 'adapted',
                          changes=CHANGES if filename == 'software_skills.csv' else '')
            version.refresh_from_db()
        row['version'] = version
    return plan
