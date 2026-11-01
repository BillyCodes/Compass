"""Authorized draft creation/editing; publication awaits the review milestone."""
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max

from accounts.permissions import require_content_editor
from .models import ContentItem, ContentVersion


@transaction.atomic
def create_content_item(*, actor, kind):
    require_content_editor(actor)
    item = ContentItem(kind=kind)
    item.full_clean()
    item.save()
    return item


@transaction.atomic
def create_draft_version(*, actor, item_id, title, body):
    require_content_editor(actor)
    # A parent row lock serializes version-number allocation for this item.
    item = ContentItem.objects.select_for_update().get(pk=item_id)
    if item.retired_at is not None:
        raise ValidationError("This content item is retired.")
    last = item.versions.aggregate(last=Max("version_no"))["last"] or 0
    version = ContentVersion(
        item=item, kind=item.kind, version_no=last + 1,
        title=title.strip(), body=body.strip(), created_by=actor,
    )
    version.full_clean()
    version.save()
    return version


@transaction.atomic
def update_draft_version(*, actor, version_id, expected_revision, title, body):
    require_content_editor(actor)
    version = ContentVersion.objects.select_for_update().get(pk=version_id)
    if version.status != ContentVersion.Status.DRAFT:
        raise ValidationError("Only draft versions can be edited.")
    if version.draft_revision != expected_revision:
        raise ValidationError("The draft changed; reload it before saving.")
    version.title = title.strip()
    version.body = body.strip()
    version.draft_revision += 1
    version.full_clean()
    version.save(update_fields=["title", "body", "draft_revision"])
    return version
