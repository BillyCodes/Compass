"""Deployment schedulers can invoke this command daily with --execute."""
from django.core.management.base import BaseCommand

from auditing.models import AuditEvent
from auditing.services import _purge_expired_events, retention_cutoff


class Command(BaseCommand):
    help = "Preview events older than one calendar year; --execute purges them."

    def add_arguments(self, parser):
        parser.add_argument("--execute", action="store_true", help="Delete events beyond the one-year retention period.")

    def handle(self, *args, **options):
        if options["execute"]:
            count = _purge_expired_events()
            self.stdout.write(f"Purged {count} expired audit event(s).")
        else:
            count = AuditEvent.objects.filter(occurred_at__lt=retention_cutoff()).count()
            self.stdout.write(f"Preview: {count} audit event(s) older than one year; use --execute to purge.")
