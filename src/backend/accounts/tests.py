"""PostgreSQL-backed tests for the first ERD section and email authentication."""
import uuid
from io import StringIO
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .models import Account, AccountRole, Role, Student
from .services import assign_role, create_student


class AccountTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.a = create_student(email="alice@example.test", password="Sample-test-only!42", display_name="Alice")
        cls.b = create_student(email="bob@example.test", password="Sample-test-only!42", display_name="Bob")
        cls.maintainer = Account.objects.create_user("fixture.maintainer@example.test", "Sample-test-only!42")
        cls.admin = Account.objects.create_user("admin@example.test", "Sample-test-only!42")
        AccountRole.objects.create(account=cls.maintainer, role=Role.objects.get(role_name="maintainer"))
        AccountRole.objects.create(account=cls.admin, role=Role.objects.get(role_name="administrator"))

    def setUp(self):
        cache.clear()

    def login(self, email="alice@example.test", password="Sample-test-only!42", **extra):
        return self.client.post(reverse("accounts:login"), {"username": email, "password": password, **extra})

    def test_email_is_normalized_and_password_hashed(self):
        account = Account.objects.create_user("  Mixed@Example.TEST  ", "Sample-test-only!42")
        self.assertEqual(account.login_email, "mixed@example.test")
        self.assertTrue(account.check_password("Sample-test-only!42"))
        self.assertNotEqual(account.password, "Sample-test-only!42")
        self.assertIsInstance(account.pk, uuid.UUID)

    def test_duplicate_email_case_is_rejected_by_database(self):
        account = Account.objects.create_user("different@example.test", "Sample-test-only!42")
        with self.assertRaises(IntegrityError), transaction.atomic():
            # Bypass save normalization to prove the database enforces this too.
            Account.objects.filter(pk=account.pk).update(login_email="ALICE@EXAMPLE.TEST")

    def test_student_profile_is_unique_and_role_is_created(self):
        self.assertTrue(self.a.account.role_assignments.filter(role__role_name="student").exists())
        with self.assertRaises(IntegrityError), transaction.atomic():
            Student.objects.create(account=self.a.account, display_name="Duplicate")

    def test_roles_are_seeded_and_constrained(self):
        self.assertSetEqual(set(Role.objects.values_list("role_name", flat=True)), {"student", "maintainer", "administrator"})
        with self.assertRaises(IntegrityError), transaction.atomic():
            Role.objects.create(role_name="unrestricted")

    def test_duplicate_role_assignment_rejected(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            AccountRole.objects.create(account=self.a.account, role=Role.objects.get(role_name="student"))

    def test_student_creation_rolls_back_if_profile_fails(self):
        with self.assertRaises(TypeError):
            create_student(email="rollback@example.test", password="Sample-test-only!42", display_name="Rollback", unknown_field=True)
        self.assertFalse(Account.objects.filter(login_email="rollback@example.test").exists())

    def test_email_login_uses_case_insensitive_matching(self):
        response = self.login(email="  ALICE@EXAMPLE.TEST  ")
        self.assertRedirects(response, reverse("accounts:profile"))
        self.assertIn("_auth_user_id", self.client.session)

    def test_invalid_and_disabled_credentials_have_same_generic_error(self):
        wrong = self.login(password="wrong")
        self.a.account.is_active = False
        self.a.account.save(update_fields=["is_active"])
        disabled = self.login()
        self.assertEqual(wrong.status_code, 200)
        self.assertEqual(disabled.status_code, 200)
        self.assertEqual(list(wrong.context["form"].non_field_errors()), list(disabled.context["form"].non_field_errors()))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_missing_account_uses_generic_error(self):
        missing = self.login(email="missing@example.test")
        wrong = self.login(password="wrong")
        self.assertEqual(list(missing.context["form"].non_field_errors()), list(wrong.context["form"].non_field_errors()))

    def test_profile_requires_login(self):
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse("accounts:login")))

    def test_student_sees_own_profile_and_not_another(self):
        self.login()
        self.assertContains(self.client.get(reverse("accounts:profile")), "Alice")
        self.assertEqual(self.client.get(reverse("accounts:student-detail", args=[self.a.pk])).status_code, 200)
        response = self.client.get(reverse("accounts:student-detail", args=[self.b.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertNotContains(response, "Bob", status_code=404)
        self.assertEqual(self.client.post(reverse("accounts:student-detail", args=[self.b.pk]), {"display_name": "Changed"}).status_code, 405)
        self.b.refresh_from_db()
        self.assertEqual(self.b.display_name, "Bob")

    def test_logout_is_post_only_and_ends_access(self):
        self.login()
        self.assertEqual(self.client.get(reverse("accounts:logout")).status_code, 405)
        self.assertRedirects(self.client.post(reverse("accounts:logout")), reverse("accounts:login"))
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(self.client.get(reverse("accounts:profile")).status_code, 302)

    def test_disabling_account_invalidates_access_on_next_request(self):
        self.login()
        self.a.account.is_active = False
        self.a.account.save(update_fields=["is_active"])
        self.assertEqual(self.client.get(reverse("accounts:profile")).status_code, 302)

    def test_maintainer_does_not_need_student_profile(self):
        response = self.login(email=self.maintainer.login_email)
        self.assertEqual(response.status_code, 302)
        self.assertContains(self.client.get(reverse("accounts:profile")), "does not have a student profile")
        self.assertEqual(self.client.get(reverse("accounts:student-detail", args=[self.a.pk])).status_code, 404)

    def test_role_assignment_requires_business_administrator(self):
        role = Role.objects.get(role_name="maintainer")
        for actor in (self.a.account, self.maintainer, AnonymousUser()):
            with self.subTest(actor=str(actor)), self.assertRaises(PermissionDenied):
                assign_role(actor=actor, account=self.a.account, role=role)
        assignment = assign_role(actor=self.admin, account=self.a.account, role=role)
        self.assertEqual(assignment.assigned_by, self.admin)
        self.a.account.refresh_from_db()
        self.assertFalse(self.a.account.is_staff)
        self.assertFalse(self.a.account.is_superuser)
        self.assertEqual(assign_role(actor=self.admin, account=self.a.account, role=role).pk, assignment.pk)

    def test_role_assigner_deletion_preserves_assignment(self):
        assignment = assign_role(actor=self.admin, account=self.a.account, role=Role.objects.get(role_name="maintainer"))
        self.admin.delete()
        assignment.refresh_from_db()
        self.assertIsNone(assignment.assigned_by)

    def test_superuser_flags_do_not_implicitly_grant_business_role(self):
        superuser = Account.objects.create_superuser("operator@example.test", "Sample-test-only!42")
        with self.assertRaises(PermissionDenied):
            assign_role(actor=superuser, account=self.a.account, role=Role.objects.get(role_name="administrator"))

    def test_csrf_protects_login_and_logout(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post(reverse("accounts:login"), {"username": "alice@example.test", "password": "Sample-test-only!42"}).status_code, 403)
        client.get(reverse("accounts:login"))
        response = client.post(reverse("accounts:login"), {
            "username": "alice@example.test", "password": "Sample-test-only!42",
            "csrfmiddlewaretoken": client.cookies["csrftoken"].value,
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(client.post(reverse("accounts:logout")).status_code, 403)
        response = client.post(reverse("accounts:logout"), {"csrfmiddlewaretoken": client.cookies["csrftoken"].value})
        self.assertEqual(response.status_code, 302)

    def test_external_next_redirect_is_rejected(self):
        self.assertRedirects(self.login(next="https://example.org/"), reverse("accounts:profile"))

    def test_password_never_echoed_and_auth_responses_not_cached(self):
        response = self.login(password="wrong-secret-sample")
        self.assertNotContains(response, "wrong-secret-sample")
        self.assertIn("no-store", response.headers["Cache-Control"])
        self.login()
        self.assertIn("no-store", self.client.get(reverse("accounts:profile")).headers["Cache-Control"])

    @override_settings(LOGIN_FAILURE_LIMIT=2)
    def test_repeated_failures_are_throttled_before_authentication(self):
        self.login(password="wrong")
        self.login(password="wrong")
        with patch("django.contrib.auth.forms.authenticate") as authenticate:
            response = self.login()
        self.assertEqual(response.status_code, 429)
        self.assertIn("Retry-After", response.headers)
        authenticate.assert_not_called()

    def test_expired_session_cannot_open_profile(self):
        self.login()
        self.client.cookies["sessionid"] = "invalid-or-expired-session"
        self.assertEqual(self.client.get(reverse("accounts:profile")).status_code, 302)

    def test_profile_text_is_escaped_and_credentials_are_not_rendered(self):
        self.a.display_name = '<img src=x onerror="alert(1)">'
        self.a.save()
        self.login()
        response = self.client.get(reverse("accounts:profile"))
        self.assertContains(response, "&lt;img")
        self.assertNotContains(response, '<img src=x onerror="alert(1)">')
        self.assertNotContains(response, self.a.account.password)

    def test_demo_setup_creates_only_unprivileged_accounts_and_refuses_overwrite(self):
        output = StringIO()
        password = "Demonstration-Only!57-Compass"
        with patch("accounts.management.commands.create_demo_accounts.getpass", return_value=password) as prompt:
            call_command("create_demo_accounts", stdout=output)
            self.assertEqual(prompt.call_count, 2)
            with self.assertRaises(CommandError):
                call_command("create_demo_accounts", stdout=output)
            self.assertEqual(prompt.call_count, 2)
        self.assertNotIn(password, output.getvalue())
        for email in ["student.a@example.test", "student.b@example.test", "maintainer@example.test"]:
            account = Account.objects.get(login_email=email)
            self.assertTrue(account.check_password(password))
            self.assertFalse(account.is_staff)
            self.assertFalse(account.is_superuser)
            self.assertFalse(account.role_assignments.filter(role__role_name="administrator").exists())
