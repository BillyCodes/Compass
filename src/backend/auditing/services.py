"""Trusted transactional writers and administrator-only event access."""
from calendar import monthrange

from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.utils import timezone

from accounts.permissions import require_role_administrator
from .models import AuditEvent


def _record_event(*, event_type, actor=None, subject=None, version=None, metadata=None):
    # Internal use only: each caller must authorize its business action first.
    # Do not use on_commit: failure to log must roll back the action itself.
    if not connection.in_atomic_block:
        raise RuntimeError("Record an audit event inside the business transaction.")
    event = AuditEvent(event_type=event_type, actor_account=actor, subject_account=subject,
                       content_version=version, metadata={} if metadata is None else metadata)
    event.full_clean()
    event.save()
    return event


def list_audit_events(*, actor, event_type=None):
    require_role_administrator(actor)
    events = AuditEvent.objects.select_related("actor_account", "subject_account", "content_version")
    if event_type is not None:
        if event_type not in AuditEvent.Type.values:
            raise ValidationError("Choose a supported audit event type.")
        events = events.filter(event_type=event_type)
    return events


def get_audit_event(*, actor, event_id):
    return list_audit_events(actor=actor).get(pk=event_id)


def retention_cutoff(now=None):
    """One calendar year, using UTC and February 28 for a leap-day anniversary."""
    from datetime import UTC
    now = (now or timezone.now()).astimezone(UTC)
    previous_year = now.year - 1
    return now.replace(year=previous_year, day=min(now.day, monthrange(previous_year, now.month)[1]))


@transaction.atomic
def _purge_expired_events():
    # Trusted management command only, never a student-facing service.
    # A PostgreSQL guard independently rejects deletion within retention.
    deleted, _ = AuditEvent.objects.filter(occurred_at__lt=retention_cutoff()).delete()
    return deleted
