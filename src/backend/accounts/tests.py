"""PostgreSQL-backed tests for the first ERD section and email authentication."""
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from io import StringIO
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, transaction, close_old_connections
from django.test import Client, TestCase, TransactionTestCase, override_settings
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
        self.assertRedirects(response, reverse("core:dashboard"))
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
        self.assertRedirects(response, reverse("maintenance:dashboard"))
        self.assertContains(self.client.get(reverse("accounts:profile")), "does not have a student profile")
        self.assertEqual(self.client.get(reverse("accounts:student-detail", args=[self.a.pk])).status_code, 404)

    def test_administrator_login_defaults_to_maintainer_dashboard(self):
        self.assertRedirects(self.login(email=self.admin.login_email), reverse("maintenance:dashboard"))

    def test_content_editor_role_takes_precedence_over_student_default(self):
        AccountRole.objects.create(account=self.a.account, role=Role.objects.get(role_name="maintainer"))
        self.assertRedirects(self.login(), reverse("maintenance:dashboard"))

    def test_maintainer_safe_next_destination_takes_precedence(self):
        self.assertRedirects(
            self.login(email=self.maintainer.login_email, next=reverse("accounts:profile")),
            reverse("accounts:profile"),
        )

    def test_maintainer_external_next_falls_back_to_maintainer_dashboard(self):
        self.assertRedirects(
            self.login(email=self.maintainer.login_email, next="https://example.org/"),
            reverse("maintenance:dashboard"),
        )

    def test_account_without_business_role_defaults_to_profile(self):
        account = Account.objects.create_superuser("login.operator@example.test", "Sample-test-only!42")
        self.assertRedirects(self.login(email=account.login_email), reverse("accounts:profile"))

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
        self.assertRedirects(self.login(next="https://example.org/"), reverse("core:dashboard"))

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


class AccountProvisioningTests(TestCase):
    PASSWORD = "Provisioning-passphrase!6284"
    NEW_PASSWORD = "Maintainer-passphrase!3197"

    def setUp(self):
        cache.clear()

    def bootstrap(self, email="owner@example.test", passwords=None):
        output = StringIO()
        with patch("accounts.management.provisioning.getpass", side_effect=passwords or [self.PASSWORD, self.PASSWORD]):
            call_command("bootstrap_administrator", email, stdout=output)
        self.assertNotIn(self.PASSWORD, output.getvalue())
        return Account.objects.get(login_email=email.lower()), output

    def manage(self, action, email, administrator="owner@example.test", password=None, new_passwords=None):
        output = StringIO()
        with (patch("accounts.management.commands.manage_maintainer.hidden_password", return_value=password or self.PASSWORD),
              patch("accounts.management.provisioning.getpass", side_effect=new_passwords or [self.NEW_PASSWORD, self.NEW_PASSWORD])):
            call_command("manage_maintainer", action, email, administrator=administrator, stdout=output)
        self.assertNotIn(self.PASSWORD, output.getvalue())
        self.assertNotIn(self.NEW_PASSWORD, output.getvalue())
        return output

    def test_bootstrap_creates_only_business_administrator_with_audited_hashed_password(self):
        from auditing.models import AuditEvent
        account, output = self.bootstrap()
        self.assertTrue(account.check_password(self.PASSWORD))
        self.assertNotEqual(account.password, self.PASSWORD)
        self.assertFalse(account.is_staff or account.is_superuser)
        self.assertFalse(Student.objects.filter(account=account).exists())
        self.assertEqual(list(account.role_assignments.values_list("role__role_name", flat=True)), ["administrator"])
        event = AuditEvent.objects.get(subject_account=account)
        self.assertIsNone(event.actor_account)
        self.assertEqual(event.metadata, {"role_name": "administrator"})
        self.assertContains(self.client.get(reverse("accounts:login")), "Log in")
        response = self.client.post(reverse("accounts:login"), {"username": account.login_email, "password": self.PASSWORD})
        self.assertRedirects(response, reverse("maintenance:dashboard"))

    def test_bootstrap_never_replaces_an_existing_or_disabled_administrator(self):
        from auditing.models import AuditEvent
        account, _ = self.bootstrap()
        initial = account.password
        Account.objects.filter(pk=account.pk).update(is_active=False)
        for email in (account.login_email, "another@example.test"):
            with patch("accounts.management.provisioning.getpass") as prompt, self.assertRaises(CommandError):
                call_command("bootstrap_administrator", email, stdout=StringIO())
            prompt.assert_not_called()
        account.refresh_from_db()
        self.assertEqual(account.password, initial)
        self.assertEqual(Account.objects.count(), 1)
        self.assertEqual(AuditEvent.objects.count(), 1)

    def test_bootstrap_does_not_promote_existing_student(self):
        student = create_student(email="student@example.test", password=self.PASSWORD, display_name="Student")
        with self.assertRaises(CommandError):
            self.bootstrap(student.account.login_email)
        self.assertFalse(student.account.role_assignments.filter(role__role_name="administrator").exists())

    def test_bootstrap_rejects_invalid_email_weak_password_and_mismatch_without_writes(self):
        for email, passwords in (("invalid", None), ("valid@example.test", ["password", "password"]),
                                  ("valid@example.test", [self.PASSWORD, "different"])):
            with self.subTest(email=email, passwords=passwords), self.assertRaises(CommandError):
                self.bootstrap(email, passwords)
            self.assertFalse(Account.objects.exists())

    def test_bootstrap_audit_failure_rolls_back_account_and_role(self):
        with patch("accounts.provisioning._record_event", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaises(RuntimeError):
                self.bootstrap()
        self.assertFalse(Account.objects.exists())
        self.assertFalse(AccountRole.objects.exists())

    def test_bootstrap_refuses_password_input_that_cannot_be_hidden(self):
        from getpass import GetPassWarning
        with patch("accounts.management.provisioning.getpass", side_effect=GetPassWarning("Cannot hide input")):
            with self.assertRaisesMessage(CommandError, "interactive terminal"):
                call_command("bootstrap_administrator", "owner@example.test", stdout=StringIO())
        self.assertFalse(Account.objects.exists())

    def test_create_maintainer_is_audited_and_uses_standard_login(self):
        from auditing.models import AuditEvent
        admin, _ = self.bootstrap()
        self.manage("create", "Editor@Example.TEST")
        editor = Account.objects.get(login_email="editor@example.test")
        self.assertTrue(editor.check_password(self.NEW_PASSWORD))
        self.assertFalse(editor.is_staff or editor.is_superuser)
        self.assertFalse(Student.objects.filter(account=editor).exists())
        self.assertEqual(list(editor.role_assignments.values_list("role__role_name", flat=True)), ["maintainer"])
        self.assertEqual(AuditEvent.objects.get(subject_account=editor).actor_account_id, admin.pk)
        response = self.client.post(reverse("accounts:login"), {"username": editor.login_email, "password": self.NEW_PASSWORD})
        self.assertRedirects(response, reverse("maintenance:dashboard"))
        self.assertEqual(self.client.get(reverse("skills:skillprint")).status_code, 403)

    def test_create_refuses_existing_account_without_resetting_credentials(self):
        self.bootstrap()
        original = Account.objects.create_user("existing@example.test", self.PASSWORD)
        with self.assertRaises(CommandError):
            self.manage("create", "EXISTING@example.test")
        original.refresh_from_db()
        self.assertTrue(original.check_password(self.PASSWORD))
        self.assertFalse(original.role_assignments.exists())

    def test_grant_and_revoke_are_idempotent_and_revoke_takes_effect_in_existing_session(self):
        from auditing.models import AuditEvent
        self.bootstrap()
        editor = Account.objects.create_user("existing@example.test", self.NEW_PASSWORD)
        for _ in range(2):
            self.manage("grant", editor.login_email)
        self.assertTrue(self.client.login(username=editor.login_email, password=self.NEW_PASSWORD))
        self.assertEqual(self.client.get(reverse("maintenance:dashboard")).status_code, 200)
        for _ in range(2):
            self.manage("revoke", editor.login_email)
        self.assertEqual(self.client.get(reverse("maintenance:dashboard")).status_code, 403)
        events = AuditEvent.objects.filter(subject_account=editor)
        self.assertEqual(events.filter(event_type="role.assigned").count(), 1)
        self.assertEqual(events.filter(event_type="role.removed").count(), 1)
        editor.refresh_from_db()
        self.assertTrue(editor.check_password(self.NEW_PASSWORD))

    def test_grant_does_not_turn_a_student_into_a_dual_role_account(self):
        self.bootstrap()
        student = create_student(email="student@example.test", password=self.PASSWORD, display_name="Student")
        with self.assertRaises(CommandError):
            self.manage("grant", student.account.login_email)
        self.assertFalse(student.account.role_assignments.filter(role__role_name="maintainer").exists())

    def test_commands_require_active_administrator_credentials_and_business_role(self):
        admin, _ = self.bootstrap()
        staff = Account.objects.create_superuser("staff@example.test", self.PASSWORD)
        editor = Account.objects.create_user("editor@example.test", self.PASSWORD)
        AccountRole.objects.create(account=editor, role=Role.objects.get(role_name="maintainer"))
        for email, password in ((admin.login_email, "wrong"), (staff.login_email, self.PASSWORD),
                                 (editor.login_email, self.PASSWORD), ("missing@example.test", self.PASSWORD)):
            with self.subTest(email=email), self.assertRaises(CommandError):
                self.manage("create", "blocked@example.test", administrator=email, password=password)
        Account.objects.filter(pk=admin.pk).update(is_active=False)
        with self.assertRaises(CommandError):
            self.manage("create", "blocked@example.test")
        self.assertFalse(Account.objects.filter(login_email="blocked@example.test").exists())

    def test_maintainer_creation_rejects_bad_password_and_rolls_back_on_audit_failure(self):
        self.bootstrap()
        for values in (["password", "password"], [self.NEW_PASSWORD, "different"]):
            with self.assertRaises(CommandError):
                self.manage("create", "blocked@example.test", new_passwords=values)
        with patch("accounts.services._record_event", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaises(RuntimeError):
                self.manage("create", "blocked@example.test")
        self.assertFalse(Account.objects.filter(login_email="blocked@example.test").exists())

    def test_deactivation_ends_maintainer_access_without_touching_student_records(self):
        from accounts.services import set_account_active
        admin, _ = self.bootstrap()
        self.manage("create", "editor@example.test")
        editor = Account.objects.get(login_email="editor@example.test")
        student = create_student(email="student@example.test", password=self.PASSWORD, display_name="Student")
        self.client.force_login(editor)
        self.assertEqual(self.client.get(reverse("accounts:student-detail", args=[student.pk])).status_code, 404)
        set_account_active(actor=admin, account=editor, is_active=False)
        self.assertEqual(self.client.get(reverse("maintenance:dashboard")).status_code, 302)
        self.assertTrue(Student.objects.filter(pk=student.pk).exists())


class AdministratorBootstrapConcurrencyTests(TransactionTestCase):
    def test_two_concurrent_bootstraps_create_only_one_administrator(self):
        from accounts.provisioning import _bootstrap_administrator
        Role.objects.get_or_create(role_name="administrator")
        barrier = Barrier(2)

        def bootstrap(email):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                try:
                    _bootstrap_administrator(email=email, password="Concurrent-bootstrap!7259")
                    return True
                except ValidationError:
                    return False
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(bootstrap, ["first@example.test", "second@example.test"]))
        self.assertEqual(sorted(outcomes), [False, True])
        self.assertEqual(AccountRole.objects.filter(role__role_name="administrator").count(), 1)
        self.assertEqual(Account.objects.count(), 1)
