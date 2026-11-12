"""One-time administrator setup authorized by local management-command access."""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError

from accounts.management.provisioning import prompt_new_password, readable_error
from accounts.models import Account, AccountRole, Role
from accounts.provisioning import _bootstrap_administrator, normalized_email


class Command(BaseCommand):
    help = "Create the first Compass business administrator; prompt for a password."

    def add_arguments(self, parser):
        parser.add_argument("email", help="Email for a new administrator account.")

    def handle(self, *args, **options):
        self.stdout.write(f"Database: {settings.DATABASES['default']['NAME']}")
        try:
            email = normalized_email(options["email"])
            if AccountRole.objects.filter(role__role_name=Role.Name.ADMINISTRATOR).exists():
                raise CommandError("An administrator already exists. Bootstrap does not replace it or reset passwords.")
            if Account.objects.filter(login_email__iexact=email).exists():
                raise CommandError("This email already has an account. Bootstrap creates a new account only.")
            account = _bootstrap_administrator(email=email, password=prompt_new_password())
        except Role.DoesNotExist:
            raise CommandError("Required roles are missing. Run manage.py migrate first.") from None
        except ValidationError as exc:
            raise readable_error(exc) from None
        except IntegrityError as exc:
            if getattr(getattr(exc.__cause__, "diag", None), "constraint_name", "") not in (
                "account_email_ci_unique", "account_login_email_key"):
                raise
            raise CommandError("This email was registered concurrently. No existing account was changed.") from None
        self.stdout.write(self.style.SUCCESS(f"Created Compass administrator: {account.login_email}"))
        self.stdout.write("Use the standard login page. This account has no student profile or Django admin privileges.")
