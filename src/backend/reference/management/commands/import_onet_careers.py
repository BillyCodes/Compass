from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management.base import BaseCommand, CommandError
from accounts.models import Account
from reference.onet_import import import_careers


class Command(BaseCommand):
    help = 'Preview the five selected O*NET career drafts; --apply writes drafts only.'

    def add_arguments(self, parser):
        parser.add_argument('--actor', required=True, help='Active maintainer/administrator email')
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--source-dir', help='Directory containing the two original O*NET 31.0 CSVs')

    def handle(self, *args, **options):
        try:
            actor = Account.objects.get(login_email__iexact=options['actor'])
            plan = import_careers(actor=actor, dry_run=not options['apply'], directory=options['source_dir'])
        except (Account.DoesNotExist, PermissionDenied, ValidationError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write('Applied draft imports and skill catalog additions; no publication.' if options['apply'] else 'Dry run: no database changes.')
        for row in plan:
            self.stdout.write(f'{row["code"]}: {row["title"]} — {row["action"]}; skills: {", ".join(row["skills"])}')
