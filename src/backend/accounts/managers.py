"""Account creation and consistent email lookup for Django authentication."""
from django.contrib.auth.base_user import BaseUserManager
from django.core.validators import validate_email


class AccountManager(BaseUserManager):
    use_in_migrations = True

    @classmethod
    def normalize_email(cls, email):
        # Compass deliberately treats the entire address as case-insensitive.
        return (email or "").strip().lower()

    def get_by_natural_key(self, email):
        return self.get(login_email__iexact=self.normalize_email(email))

    def create_user(self, login_email, password=None, **extra_fields):
        if not self.normalize_email(login_email):
            raise ValueError("An email address is required.")
        email = self.normalize_email(login_email)
        validate_email(email)
        account = self.model(login_email=email, **extra_fields)
        account.set_password(password)  # Django hashes it; never assign plaintext.
        account.save(using=self._db)
        return account

    def create_superuser(self, login_email, password=None, **extra_fields):
        for flag in ("is_staff", "is_superuser", "is_active"):
            extra_fields.setdefault(flag, True)
            if extra_fields[flag] is not True:
                raise ValueError(f"A superuser must have {flag}=True.")
        return self.create_user(login_email, password, **extra_fields)
