"""Create synthetic login accounts without storing passwords in repository files."""
from getpass import getpass

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import Account, AccountRole, Role
from accounts.services import create_student


class Command(BaseCommand):
    help = "Create synthetic student and maintainer accounts; prompt for a shared demo password."

    @transaction.atomic
    def handle(self, *args, **options):
        emails = ["student.a@example.test", "student.b@example.test", "maintainer@example.test"]
        if Account.objects.filter(login_email__in=emails).exists():
            raise CommandError("Demo accounts already exist; existing credentials were not changed.")
        password = getpass("Demo password (synthetic accounts only): ")
        if password != getpass("Confirm demo password: "):
            raise CommandError("Passwords do not match.")
        try:
            for email in emails:
                validate_password(password, user=Account(login_email=email))
        except ValidationError as exc:
            raise CommandError("; ".join(exc.messages)) from exc
        create_student(email=emails[0], password=password, display_name="Sample Student A")
        create_student(email=emails[1], password=password, display_name="Sample Student B")
        maintainer = Account.objects.create_user(emails[2], password)
        AccountRole.objects.create(account=maintainer, role=Role.objects.get(role_name="maintainer"))
        self.stdout.write(self.style.SUCCESS("Created synthetic accounts: " + ", ".join(emails)))
        self.stdout.write("No staff, superuser, or administrator privileges were granted.")
