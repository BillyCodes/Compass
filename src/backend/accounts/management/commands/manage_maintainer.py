"""Authenticate an administrator before creating or changing maintainer access."""
from django.conf import settings
from django.contrib.auth import authenticate
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError

from accounts.management.provisioning import hidden_password, prompt_new_password, readable_error
from accounts.models import Account, Role
from accounts.permissions import require_role_administrator
from accounts.provisioning import change_maintainer_access, create_maintainer, normalized_email


class Command(BaseCommand):
    help = "Create, grant or revoke a maintainer account after authenticating a Compass administrator."

    def add_arguments(self, parser):
        parser.add_argument("action", choices=["create", "grant", "revoke"])
        parser.add_argument("email", help="Target account email; create refuses existing accounts.")
        parser.add_argument("--administrator", required=True, help="Existing administrator email; password is prompted.")

    def handle(self, *args, **options):
        self.stdout.write(f"Database: {settings.DATABASES['default']['NAME']}")
        try:
            email = normalized_email(options["email"])
            administrator = normalized_email(options["administrator"])
            actor = authenticate(username=administrator, password=hidden_password("Administrator password: "))
            if actor is None:
                raise CommandError("An active Compass administrator and valid password are required.")
            require_role_administrator(actor)
            if options["action"] == "create":
                if Account.objects.filter(login_email__iexact=email).exists():
                    raise CommandError("This email already has an account. Use grant explicitly for a non-student account; credentials were not changed.")
                account = create_maintainer(actor=actor, email=email, password=prompt_new_password())
            else:
                account = change_maintainer_access(actor=actor, email=email, grant=options["action"] == "grant")
        except PermissionDenied:
            raise CommandError("An active Compass business administrator role is required; staff/superuser flags alone are insufficient.") from None
        except Account.DoesNotExist:
            raise CommandError("Target account not found. Use create for a new maintainer.") from None
        except Role.DoesNotExist:
            raise CommandError("Required roles are missing. Run manage.py migrate first.") from None
        except ValidationError as exc:
            raise readable_error(exc) from None
        except IntegrityError as exc:
            if getattr(getattr(exc.__cause__, "diag", None), "constraint_name", "") not in (
                "account_email_ci_unique", "account_login_email_key"):
                raise
            raise CommandError("This email was registered concurrently. No existing credentials were changed.") from None
        self.stdout.write(self.style.SUCCESS(f"Maintainer {options['action']} completed: {account.login_email}"))
        if options["action"] != "revoke":
            self.stdout.write("Use the standard login page; the default destination is /maintainer/.")
        else:
            self.stdout.write("The maintainer role is absent. Other assigned roles, if any, still apply.")
