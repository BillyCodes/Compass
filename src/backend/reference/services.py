"""Authorized reference editing, independent review, publication, and retirement."""
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Max
from django.utils import timezone

from accounts.permissions import require_content_editor
from auditing.models import AuditEvent
from auditing.services import _record_event
from skills.models import Skill
from .models import (
    Company, ContentDetails, ContentItem, ContentKind, ContentRequirement,
    ContentReview, ContentSkill, ContentSource, ContentVersion, ReferenceSource,
    SOURCE_METADATA_FIELDS, SOURCE_USAGE_FIELDS,
)


@transaction.atomic
def create_content_item(*, actor, kind):
    require_content_editor(actor)
    item = ContentItem(kind=kind)
    item.full_clean()
    item.save()
    return item


@transaction.atomic
def create_draft_version(*, actor, item_id, title, body, origin=ContentVersion.Origin.SYNTHETIC,
                         original_author="", originality_confirmed=False):
    require_content_editor(actor)
    if type(originality_confirmed) is not bool:
        raise ValidationError("Confirm originality using a checkbox.")
    # A parent row lock serializes version-number allocation for this item.
    item = ContentItem.objects.select_for_update().get(pk=item_id)
    if item.retired_at is not None:
        raise ValidationError("This content item is retired.")
    last = item.versions.aggregate(last=Max("version_no"))["last"] or 0
    version = ContentVersion(
        item=item, kind=item.kind, version_no=last + 1,
        title=title.strip(), body=body.strip(), created_by=actor,
        origin=origin, original_author=_text(original_author, "original_author"),
        originality_confirmed=originality_confirmed,
    )
    version.full_clean()
    version.save()
    return version


@transaction.atomic
def create_successor_draft(*, actor, version_id):
    """Copy an immutable edition into its item's next editable draft.

    An existing draft is opened instead of creating duplicates on repeated POSTs.
    Sources/company identities stay shared; corrections to frozen references use
    the existing replacement services. Reviews and publication attribution do not
    carry forward.
    """
    require_content_editor(actor)
    identity = ContentVersion.objects.only("item_id").get(pk=version_id)
    item = ContentItem.objects.select_for_update().get(pk=identity.item_id)
    source = ContentVersion.objects.select_for_update().get(pk=version_id)
    if item.retired_at is not None:
        raise ValidationError("This content item is retired.")
    if source.status not in (ContentVersion.Status.PUBLISHED, ContentVersion.Status.RETIRED):
        raise ValidationError("Create a successor from a published or retired edition.")
    existing = item.versions.filter(status=ContentVersion.Status.DRAFT).order_by("-version_no").first()
    if existing is not None:
        return existing
    version = create_draft_version(actor=actor, item_id=item.pk, title=source.title, body=source.body,
        origin=source.origin, original_author=source.original_author, originality_confirmed=False)
    ContentSource.objects.bulk_create([
        ContentSource(version=version, source_id=link.source_id,
                      **{field: getattr(link, field) for field in SOURCE_USAGE_FIELDS})
        for link in source.source_links.all()
    ])
    ContentRequirement.objects.bulk_create([
        ContentRequirement(version=version, kind=version.kind, skill_id=row.skill_id,
                           required_level=row.required_level, weight=row.weight, mandatory=row.mandatory)
        for row in source.requirements.all()
    ])
    ContentSkill.objects.bulk_create([
        ContentSkill(version=version, kind=version.kind, skill_id=row.skill_id, coverage_level=row.coverage_level)
        for row in source.skill_mappings.all()
    ])
    details = getattr(source, "details", None)
    if details is not None:
        fields = {field.attname: getattr(details, field.attname)
                  for field in ContentDetails._meta.concrete_fields if field.name != "version"}
        ContentDetails.objects.create(version=version, **fields)
    # Pilot author cards/tags belong to their edition and must be copied before
    # publication, while the new draft can still be edited.
    profile = getattr(source, "field_note", None)
    if profile is not None:
        fields = {field.attname: getattr(profile, field.attname)
                  for field in type(profile)._meta.concrete_fields if field.name != "version"}
        copied = type(profile).objects.create(version=version, **fields)
        copied.skills.set(profile.skills.all())
    version.refresh_from_db()
    return version


@transaction.atomic
def update_draft_version(*, actor, version_id, expected_revision, title, body, origin=None,
                         original_author=None, originality_confirmed=None):
    version = _lock_draft(actor, version_id, expected_revision)
    version.title = title.strip()
    version.body = body.strip()
    if origin is not None:
        version.origin = origin
    if original_author is not None:
        version.original_author = _text(original_author, "original_author")
    if originality_confirmed is not None:
        if type(originality_confirmed) is not bool:
            raise ValidationError("Confirm originality using a checkbox.")
        version.originality_confirmed = originality_confirmed
    version.draft_revision += 1
    version.full_clean()
    version.save(update_fields=["title", "body", "draft_revision", "origin", "original_author", "originality_confirmed"])
    return version


def _lock_draft(actor, version_id, expected_revision):
    """Shared guard for text edits and every related draft-data mutation."""
    require_content_editor(actor)
    version = ContentVersion.objects.select_for_update().get(pk=version_id)
    if version.status != ContentVersion.Status.DRAFT:
        raise ValidationError("Only draft versions can be edited.")
    if version.item.retired_at is not None:
        raise ValidationError("This content item is retired.")
    if type(expected_revision) is not int or expected_revision < 1:
        raise ValidationError("A positive integer draft revision is required.")
    if version.draft_revision != expected_revision:
        raise ValidationError("The draft changed; reload it before saving.")
    return version


def _touch_revision(version):
    # Child/shared-reference triggers advance the revision in the same transaction.
    # Refresh rather than incrementing again in Python.
    version.refresh_from_db(fields=["draft_revision"])


def _text(value, field):
    if not isinstance(value, str):
        raise ValidationError({field: "Use plain text."})
    return value.strip()


def _level(value, field):
    if type(value) is not int or not 0 <= value <= 5:
        raise ValidationError({field: "Choose an integer from 0 to 5."})
    return value


def _decimal(value, field):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValidationError({field: "Use a finite nonnegative number."}) from None
    if not result.is_finite() or result < 0:
        raise ValidationError({field: "Use a finite nonnegative number."})
    return result


@transaction.atomic
def create_company(*, actor, company_name, industry=""):
    require_content_editor(actor)
    company = Company(company_name=_text(company_name,"company_name"), industry=_text(industry,"industry"))
    company.full_clean()
    company.save()
    return company


@transaction.atomic
def create_reference_source(*, actor, source_title, source_url_or_identifier, collected_at=None, **metadata):
    require_content_editor(actor)
    fields = {
        "source_title": _text(source_title,"source_title"),
        "source_url_or_identifier": _text(source_url_or_identifier,"source_url_or_identifier"),
    }
    if collected_at is not None:
        fields["collected_at"] = collected_at
    if set(metadata) - set(SOURCE_METADATA_FIELDS):
        raise ValidationError("Unsupported source metadata.")
    fields.update({key: value if key == "raw_metadata" else _text(value, key) for key, value in metadata.items()})
    source = ReferenceSource(**fields)
    source.full_clean()
    source.save()
    return source


@transaction.atomic
def attach_source(*, actor, version_id, source_id, expected_revision, usage=ContentSource.Usage.UNKNOWN,
                  changes="", attribution_note=""):
    version = _lock_draft(actor,version_id,expected_revision)
    source = ReferenceSource.objects.get(pk=source_id)
    existing = ContentSource.objects.filter(version=version,source=source).first()
    if existing is not None:
        return existing  # No content change, so do not increment the revision.
    link = ContentSource(version=version,source=source,usage=usage,
                         changes=_text(changes, "changes"), attribution_note=_text(attribution_note, "attribution_note"))
    link.full_clean()
    link.save()
    _touch_revision(version)
    return link


@transaction.atomic
def set_requirement(*, actor, version_id, skill_id, required_level, mandatory, weight, expected_revision):
    version = _lock_draft(actor,version_id,expected_revision)
    if version.kind not in (ContentKind.CAREER, ContentKind.JOB):
        raise ValidationError("Only career/job versions have requirements.")
    skill = Skill.objects.select_for_update().get(pk=skill_id)
    if skill.status != Skill.Status.ACTIVE:
        raise ValidationError("This skill is retired.")
    if type(mandatory) is not bool:
        raise ValidationError({"mandatory": "Use a boolean value."})
    record = ContentRequirement.objects.filter(version=version,skill=skill).first()
    if record is None:
        record = ContentRequirement(version=version,skill=skill,kind=version.kind)
    record.required_level = _level(required_level,"required_level")
    record.mandatory = mandatory
    record.weight = _decimal(weight,"weight")
    record.full_clean()
    record.save()
    _touch_revision(version)
    return record


@transaction.atomic
def set_skill_mapping(*, actor, version_id, skill_id, coverage_level, expected_revision):
    version = _lock_draft(actor,version_id,expected_revision)
    if version.kind not in (ContentKind.COURSE, ContentKind.RESOURCE):
        raise ValidationError("Only course/resource versions have learning mappings.")
    skill = Skill.objects.select_for_update().get(pk=skill_id)
    if skill.status != Skill.Status.ACTIVE:
        raise ValidationError("This skill is retired.")
    record = ContentSkill.objects.filter(version=version,skill=skill).first()
    if record is None:
        record = ContentSkill(version=version,skill=skill,kind=version.kind)
    record.coverage_level = _level(coverage_level,"coverage_level")
    record.full_clean()
    record.save()
    _touch_revision(version)
    return record


@transaction.atomic
def set_content_details(
    *, actor, version_id, expected_revision, company_id=None, location="",
    expires_at=None, course_code="", credits=None, provider="", resource_url="",
    cost_amount=None, currency="",
):
    """Replace the complete details state; omitted optional fields are cleared."""
    version = _lock_draft(actor,version_id,expected_revision)
    record = ContentDetails.objects.filter(version=version).first()
    if record is None:
        record = ContentDetails(version=version,kind=version.kind)
    record.company_id = company_id
    record.expires_at = expires_at
    for field,value in {
        "location":location, "course_code":course_code, "provider":provider,
        "resource_url":resource_url, "currency":currency,
    }.items():
        setattr(record,field,_text(value,field))
    record.currency = record.currency.upper()
    record.credits = None if credits is None else _decimal(credits,"credits")
    record.cost_amount = None if cost_amount is None else _decimal(cost_amount,"cost_amount")
    record.full_clean()
    record.save()
    _touch_revision(version)
    return record


def _remove_draft_link(actor, version_id, expected_revision, model, **lookup):
    version = _lock_draft(actor,version_id,expected_revision)
    deleted, _ = model.objects.filter(version=version,**lookup).delete()
    if deleted:
        _touch_revision(version)
    return bool(deleted)


@transaction.atomic
def detach_source(*, actor, version_id, source_id, expected_revision):
    return _remove_draft_link(actor,version_id,expected_revision,ContentSource,source_id=source_id)


@transaction.atomic
def remove_requirement(*, actor, version_id, skill_id, expected_revision):
    return _remove_draft_link(actor,version_id,expected_revision,ContentRequirement,skill_id=skill_id)


@transaction.atomic
def remove_skill_mapping(*, actor, version_id, skill_id, expected_revision):
    return _remove_draft_link(actor,version_id,expected_revision,ContentSkill,skill_id=skill_id)


@transaction.atomic
def clear_content_details(*, actor, version_id, expected_revision):
    return _remove_draft_link(actor,version_id,expected_revision,ContentDetails)


@transaction.atomic
def review_content_version(*, actor, version_id, expected_revision, decision, review_note=""):
    version = _lock_draft(actor, version_id, expected_revision)
    if actor.pk == version.created_by_id:
        raise ValidationError("The draft author cannot review their own content.")
    latest = version.reviews.filter(reviewed_revision=version.draft_revision).order_by("-reviewed_at", "-review_id").first()
    reviewed_at = timezone.now()
    if latest is not None:
        reviewed_at = max(reviewed_at, latest.reviewed_at + timedelta(microseconds=1))
    review = ContentReview(
        version=version, reviewer=actor, reviewed_revision=version.draft_revision,
        decision=decision, review_note=_text(review_note,"review_note"), reviewed_at=reviewed_at,
    )
    review.full_clean()
    review.save()
    _record_event(event_type=AuditEvent.Type.CONTENT_REVIEWED, actor=actor, version=version,
                  metadata={"decision": review.decision, "reviewed_revision": review.reviewed_revision})
    return review


@transaction.atomic
def publish_content_version(*, actor, version_id, expected_revision):
    version = _lock_draft(actor, version_id, expected_revision)
    # Revalidate application-level fields (notably complete URL syntax) as well
    # as the database's relationship/completeness guards.
    details = ContentDetails.objects.filter(version=version).first()
    if details is not None:
        details.full_clean()
    for link in version.source_links.select_related("source"):
        link.full_clean()
        link.source.full_clean()
    version.status = ContentVersion.Status.PUBLISHED
    version.published_by = actor
    version.published_at = timezone.now()
    version.full_clean()
    # The database trigger is the single publication-policy validator, including
    # current independent approval, sources, and type-specific completeness.
    try:
        with transaction.atomic():
            version.save(update_fields=["status", "published_by", "published_at"])
    except IntegrityError as exc:
        if getattr(exc.__cause__, "sqlstate", None) != "23514":
            raise
        message = exc.__cause__.diag.message_primary
        raise ValidationError(message) from exc
    _record_event(event_type=AuditEvent.Type.CONTENT_PUBLISHED, actor=actor, version=version)
    return version


@transaction.atomic
def retire_content_version(*, actor, version_id):
    require_content_editor(actor)
    version = ContentVersion.objects.select_for_update().get(pk=version_id)
    if version.status != ContentVersion.Status.PUBLISHED:
        raise ValidationError("Only published versions can be retired.")
    version.status = ContentVersion.Status.RETIRED
    version.save(update_fields=["status"])
    _record_event(event_type=AuditEvent.Type.CONTENT_RETIRED, actor=actor, version=version)
    return version


def available_content_versions(*, kind=None):
    versions = ContentVersion.objects.filter(status=ContentVersion.Status.PUBLISHED, item__retired_at__isnull=True)
    versions = versions.exclude(details__expires_at__lte=timezone.now())
    if kind is not None:
        versions = versions.filter(kind=kind)
    return versions


@transaction.atomic
def edit_draft_source(
    *,
    actor,
    version_id,
    source_id,
    expected_revision,
    source_title,
    source_url_or_identifier,
    **metadata,
):
    """Replace a draft's source with a corrected, separate catalog entry."""
    version = _lock_draft(actor, version_id, expected_revision)

    link = (
        ContentSource.objects
        .select_related("source")
        .filter(version=version, source_id=source_id)
        .first()
    )

    if link is None:
        raise ValidationError(
            "This source is no longer attached to the draft. Reload the page."
        )

    title = _text(source_title, "source_title")
    identifier = _text(
        source_url_or_identifier,
        "source_url_or_identifier",
    )

    original = link.source

    if set(metadata) - set(SOURCE_METADATA_FIELDS + SOURCE_USAGE_FIELDS):
        raise ValidationError("Unsupported source metadata.")
    source_fields = {field: metadata.get(field, getattr(original, field)) for field in SOURCE_METADATA_FIELDS}
    usage_fields = {field: metadata.get(field, getattr(link, field)) for field in SOURCE_USAGE_FIELDS}
    source_changed = (title != original.source_title or identifier != original.source_url_or_identifier
                      or any(value != getattr(original, field) for field, value in source_fields.items()))
    if not source_changed and all(value == getattr(link, field) for field, value in usage_fields.items()):
        return original

    corrected = create_reference_source(
        actor=actor,
        source_title=title,
        source_url_or_identifier=identifier,
        collected_at=original.collected_at,
        **source_fields,
    ) if source_changed else original

    link.source = corrected
    for field, value in usage_fields.items():
        setattr(link, field, value)
    link.full_clean()
    link.save(update_fields=["source", *SOURCE_USAGE_FIELDS])

    _touch_revision(version)

    return corrected
