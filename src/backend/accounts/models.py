"""First ERD section: account identity, optional student profile, and roles."""
import uuid

from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.db.models.functions import Lower

from .managers import AccountManager


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Account(AbstractBaseUser, PermissionsMixin, TimestampedModel):
    account_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    login_email = models.EmailField(unique=True)
    # Keep Django's password API while matching the ERD's storage column name.
    password = models.CharField(max_length=128, db_column="password_hash")
    is_active = models.BooleanField(default=True)  # ERD active/disabled status.
    is_staff = models.BooleanField(default=False)  # Django admin, not a Compass role.

    USERNAME_FIELD = "login_email"
    EMAIL_FIELD = "login_email"
    REQUIRED_FIELDS = []
    objects = AccountManager()

    class Meta:
        db_table = "account"
        constraints = [models.UniqueConstraint(Lower("login_email"), name="account_email_ci_unique")]

    def clean(self):
        super().clean()
        self.login_email = Account.objects.normalize_email(self.login_email)

    def save(self, *args, **kwargs):
        self.login_email = Account.objects.normalize_email(self.login_email)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.login_email


class Student(TimestampedModel):
    student_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="student")
    display_name = models.CharField(max_length=150)
    # Empty optional text is represented consistently as "" rather than NULL.
    major = models.CharField(max_length=150, blank=True)
    career_interests = models.TextField(blank=True)
    graduation_year = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        db_table = "student"

    def __str__(self):
        return self.display_name


class Role(models.Model):
    class Name(models.TextChoices):
        STUDENT = "student", "Student"
        MAINTAINER = "maintainer", "Maintainer"
        ADMINISTRATOR = "administrator", "Administrator"

    role_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    role_name = models.CharField(max_length=20, unique=True, choices=Name.choices)

    class Meta:
        db_table = "role"
        constraints = [models.CheckConstraint(
            condition=models.Q(role_name__in=["student", "maintainer", "administrator"]),
            name="role_name_allowed",
        )]

    def __str__(self):
        return self.role_name


class AccountRole(models.Model):
    # A surrogate UUID supports ordinary Django relations; the ERD's composite
    # identity is preserved by a unique constraint on (account, role).
    assignment_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="role_assignments")
    role = models.ForeignKey(Role, on_delete=models.PROTECT, related_name="assignments")
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="assigned_roles",
    )
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "account_role"
        constraints = [models.UniqueConstraint(fields=["account", "role"], name="account_role_unique")]
