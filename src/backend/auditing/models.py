"""Minimal event history; nullable links do not duplicate personal identifiers."""
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class AuditEvent(models.Model):
    class Type(models.TextChoices):
        ROLE_ASSIGNED = "role.assigned", "Role assigned"
        ROLE_REMOVED = "role.removed", "Role removed"
        ACCOUNT_ACTIVATED = "account.activated", "Account activated"
        ACCOUNT_DISABLED = "account.disabled", "Account disabled"
        CONTENT_REVIEWED = "content.reviewed", "Content reviewed"
        CONTENT_PUBLISHED = "content.published", "Content published"
        CONTENT_RETIRED = "content.retired", "Content retired"

    event_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor_account = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="performed_audit_events")
    subject_account = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="subject_audit_events")
    content_version = models.ForeignKey("reference.ContentVersion", on_delete=models.SET_NULL, null=True, blank=True, related_name="audit_events")
    event_type = models.CharField(max_length=30, choices=Type.choices)
    occurred_at = models.DateTimeField(default=timezone.now)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "audit_event"
        ordering = ["-occurred_at", "event_id"]
        indexes = [models.Index(fields=["event_type", "-occurred_at"], name="audit_type_time_idx"),
                   models.Index(fields=["occurred_at"], name="audit_retention_idx")]
        constraints = [models.CheckConstraint(condition=models.Q(event_type__in=[
            "role.assigned", "role.removed", "account.activated", "account.disabled",
            "content.reviewed", "content.published", "content.retired",
        ]), name="audit_event_type_allowed")]

    def clean(self):
        super().clean()
        validate_metadata(self.event_type, self.metadata)


def validate_metadata(event_type, metadata):
    """An allowlist avoids accidentally logging credentials or unrestricted text."""
    valid = isinstance(metadata, dict)
    if event_type in (AuditEvent.Type.ROLE_ASSIGNED, AuditEvent.Type.ROLE_REMOVED):
        valid = valid and set(metadata) == {"role_name"} and metadata["role_name"] in ("student", "maintainer", "administrator")
    elif event_type == AuditEvent.Type.CONTENT_REVIEWED:
        valid = (valid and set(metadata) == {"decision", "reviewed_revision"}
                 and metadata["decision"] in ("approved", "changes_requested")
                 and type(metadata["reviewed_revision"]) is int
                 and 1 <= metadata["reviewed_revision"] <= 2147483647)
    elif event_type in AuditEvent.Type.values:
        valid = valid and metadata == {}
    else:
        valid = False
    if not valid:
        raise ValidationError({"metadata": "Use only the minimal structured fields for this event type."})
