"""Audit scope, privacy, transactional recording, and calendar retention."""
from datetime import UTC, datetime, timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.db import connection, IntegrityError, transaction
from django.test import SimpleTestCase, TestCase, TransactionTestCase
from django.utils import timezone

from accounts.models import Account, AccountRole, Role
from accounts.services import assign_role, create_student, remove_role, set_account_active
from auditing.models import AuditEvent, validate_metadata
from auditing.services import _record_event, get_audit_event, list_audit_events, retention_cutoff
from reference.models import ContentReview, ContentVersion
from reference.services import publish_content_version, retire_content_version, review_content_version
from comparisons.tests.factories import approve, draft, setup_actors


class RetentionTests(SimpleTestCase):
    def test_calendar_anniversary_and_leap_day(self):
        self.assertEqual(retention_cutoff(datetime(2024,2,29,12,tzinfo=UTC)),datetime(2023,2,28,12,tzinfo=UTC))
        self.assertEqual(retention_cutoff(datetime(2025,3,1,12,tzinfo=UTC)),datetime(2024,3,1,12,tzinfo=UTC))

    def test_metadata_allowlist_rejects_arbitrary_text_and_credentials(self):
        for event_type,metadata in [
            ("role.assigned",{"role_name":"student","email":"someone@example.test"}),
            ("content.reviewed",{"decision":"approved","reviewed_revision":True}),
            ("content.reviewed",{"decision":"approved","reviewed_revision":1,"review_note":"private"}),
            ("account.disabled",{"password":"secret"}),
            ("unknown",{}),
        ]:
            with self.subTest(event_type=event_type),self.assertRaises(ValidationError):
                validate_metadata(event_type,metadata)


class AuditFixture(TestCase):
    @classmethod
    def setUpTestData(cls):
        setup_actors(cls)
        cls.admin = Account.objects.create_user("audit.admin@example.test")
        AccountRole.objects.create(account=cls.admin,role=Role.objects.get(role_name="administrator"))

    def assign(self):
        return assign_role(actor=self.admin,account=self.student.account,role=Role.objects.get(role_name="maintainer"))

    def event(self,**extra):
        fields = dict(event_type="role.assigned",subject_account=self.student.account,actor_account=self.admin,
                      metadata={"role_name":"maintainer"})
        fields.update(extra)
        return AuditEvent.objects.create(**fields)


class AccountAuditTests(AuditFixture):
    def test_trusted_student_setup_records_initial_role_without_password_or_email(self):
        student = create_student(email="audit.new@example.test",password=None,display_name="Private name",major="Private major")
        event = AuditEvent.objects.get(subject_account=student.account)
        self.assertEqual(event.event_type,"role.assigned")
        self.assertIsNone(event.actor_account)
        self.assertEqual(event.metadata,{"role_name":"student"})

    def test_assign_and_remove_record_only_actual_changes(self):
        before = AuditEvent.objects.count()
        assignment = self.assign()
        self.assign()
        self.assertEqual(AuditEvent.objects.count(),before+1)
        event = AuditEvent.objects.get(subject_account=self.student.account,event_type="role.assigned",metadata={"role_name":"maintainer"})
        self.assertEqual(event.actor_account,self.admin)
        self.assertEqual(event.metadata,{"role_name":"maintainer"})
        self.assertTrue(remove_role(actor=self.admin,account=self.student.account,role=assignment.role))
        self.assertFalse(remove_role(actor=self.admin,account=self.student.account,role=assignment.role))
        self.assertEqual(AuditEvent.objects.count(),before+2)
        self.assertTrue(AuditEvent.objects.filter(event_type="role.removed",subject_account=self.student.account).exists())

    def test_activation_service_logs_transitions_and_ignores_noops(self):
        before = AuditEvent.objects.count()
        for status in (True,False,False,True,True):
            set_account_active(actor=self.admin,account=self.student.account,is_active=status)
        self.assertEqual(AuditEvent.objects.count(),before+2)
        self.assertEqual(set(AuditEvent.objects.filter(event_type__startswith="account.").values_list("event_type",flat=True)),{"account.activated","account.disabled"})
        with self.assertRaises(ValidationError):
            set_account_active(actor=self.admin,account=self.student.account,is_active=1)

    def test_nonadministrators_cannot_manage_roles_or_status(self):
        for actor in (self.student.account,self.author,AnonymousUser()):
            for service in (assign_role,remove_role):
                with self.assertRaises(PermissionDenied):
                    service(actor=actor,account=self.other.account,role=Role.objects.get(role_name="maintainer"))
            with self.assertRaises(PermissionDenied):
                set_account_active(actor=actor,account=self.other.account,is_active=False)

    def test_audit_failure_rolls_back_role_assignment_removal_and_activation(self):
        role = Role.objects.get(role_name="maintainer")
        with patch("accounts.services._record_event",side_effect=RuntimeError("audit failure")):
            with self.assertRaises(RuntimeError):
                self.assign()
            self.assertFalse(AccountRole.objects.filter(account=self.student.account,role=role).exists())
            with self.assertRaises(RuntimeError):
                set_account_active(actor=self.admin,account=self.student.account,is_active=False)
            self.student.account.refresh_from_db()
            self.assertTrue(self.student.account.is_active)
        self.assign()
        with patch("accounts.services._record_event",side_effect=RuntimeError("audit failure")):
            with self.assertRaises(RuntimeError):
                remove_role(actor=self.admin,account=self.student.account,role=role)
        self.assertTrue(AccountRole.objects.filter(account=self.student.account,role=role).exists())

    def test_deleted_actor_and_subject_are_nulled_without_losing_history(self):
        self.assign()
        event = AuditEvent.objects.get(event_type="role.assigned",subject_account=self.student.account,metadata={"role_name":"maintainer"})
        self.admin.delete()
        self.student.account.delete()
        event.refresh_from_db()
        self.assertIsNone(event.actor_account_id)
        self.assertIsNone(event.subject_account_id)
        self.assertEqual(event.metadata,{"role_name":"maintainer"})


class ContentAuditTests(AuditFixture):
    def test_review_publication_and_retirement_have_minimal_events(self):
        version = draft(self)
        review = review_content_version(actor=self.reviewer,version_id=version.pk,expected_revision=version.draft_revision,
                                       decision="approved",review_note="Private review note")
        publish_content_version(actor=self.author,version_id=version.pk,expected_revision=version.draft_revision)
        retire_content_version(actor=self.author,version_id=version.pk)
        events = list(AuditEvent.objects.filter(content_version=version).order_by("occurred_at"))
        self.assertEqual([e.event_type for e in events],["content.reviewed","content.published","content.retired"])
        self.assertEqual(events[0].metadata,{"decision":"approved","reviewed_revision":review.reviewed_revision})
        self.assertEqual(events[0].actor_account,self.reviewer)
        self.assertEqual(events[1].metadata,{})
        self.assertEqual(events[2].metadata,{})
        self.assertNotIn("Private review note",str([e.metadata for e in events]))

    def test_changes_requested_is_a_review_event(self):
        version = draft(self)
        review_content_version(actor=self.reviewer,version_id=version.pk,expected_revision=version.draft_revision,decision="changes_requested")
        self.assertEqual(AuditEvent.objects.get(content_version=version).metadata["decision"],"changes_requested")

    def test_failed_publication_and_self_review_do_not_leave_success_events(self):
        version = draft(self)
        with self.assertRaises(ValidationError):
            review_content_version(actor=self.author,version_id=version.pk,expected_revision=version.draft_revision,decision="approved")
        with self.assertRaises(ValidationError):
            publish_content_version(actor=self.author,version_id=version.pk,expected_revision=version.draft_revision)
        self.assertFalse(AuditEvent.objects.filter(content_version=version).exists())

    def test_audit_failure_rolls_back_each_content_action(self):
        version = draft(self)
        with patch("reference.services._record_event",side_effect=RuntimeError("audit failure")):
            with self.assertRaises(RuntimeError):
                review_content_version(actor=self.reviewer,version_id=version.pk,expected_revision=version.draft_revision,decision="approved")
        self.assertFalse(ContentReview.objects.filter(version=version).exists())
        review_content_version(actor=self.reviewer,version_id=version.pk,expected_revision=version.draft_revision,decision="approved")
        with patch("reference.services._record_event",side_effect=RuntimeError("audit failure")):
            with self.assertRaises(RuntimeError):
                publish_content_version(actor=self.author,version_id=version.pk,expected_revision=version.draft_revision)
        version.refresh_from_db()
        self.assertEqual(version.status,"draft")
        publish_content_version(actor=self.author,version_id=version.pk,expected_revision=version.draft_revision)
        with patch("reference.services._record_event",side_effect=RuntimeError("audit failure")):
            with self.assertRaises(RuntimeError):
                retire_content_version(actor=self.author,version_id=version.pk)
        version.refresh_from_db()
        self.assertEqual(version.status,"published")

    def test_outer_transaction_rollback_removes_action_and_event(self):
        version = draft(self)
        with self.assertRaises(RuntimeError),transaction.atomic():
            approve(self,version)
            raise RuntimeError("outer failure")
        version.refresh_from_db()
        self.assertEqual(version.status,"draft")
        self.assertFalse(ContentReview.objects.filter(version=version).exists())
        self.assertFalse(AuditEvent.objects.filter(content_version=version).exists())

    def test_content_link_can_be_cleared_by_parent_deletion(self):
        # A draft with an event link exercises SET_NULL independently of review
        # rows, which intentionally protect reviewed reference history.
        from reference.services import create_content_item,create_draft_version
        item = create_content_item(actor=self.author,kind="insight")
        version = create_draft_version(actor=self.author,item_id=item.pk,title="Link test",body="Body")
        event = self.event(event_type="content.published",subject_account=None,content_version=version,metadata={})
        version.delete()
        event.refresh_from_db()
        self.assertIsNone(event.content_version_id)


class AuditAccessAndIntegrityTests(AuditFixture):
    def test_only_active_business_administrators_can_read(self):
        event = self.event()
        self.assertEqual(get_audit_event(actor=self.admin,event_id=event.pk),event)
        self.assertTrue(list_audit_events(actor=self.admin,event_type="role.assigned").exists())
        superuser = Account.objects.create_superuser("audit.operator@example.test","Synthetic-pass-42!")
        for actor in (AnonymousUser(),self.student.account,self.author,superuser):
            with self.assertRaises(PermissionDenied):
                list_audit_events(actor=actor)
            with self.assertRaises(PermissionDenied):
                get_audit_event(actor=actor,event_id=event.pk)
        # Use a stale actor object to verify persisted disabled status is checked.
        Account.objects.filter(pk=self.admin.pk).update(is_active=False)
        with self.assertRaises(PermissionDenied):
            list_audit_events(actor=self.admin)

    def test_filter_rejects_unknown_event_type(self):
        with self.assertRaises(ValidationError):
            list_audit_events(actor=self.admin,event_type="login.password")

    def test_database_rejects_editing_events_or_reassigning_links(self):
        event = self.event()
        for fields in ({"metadata":{"role_name":"student"}},{"occurred_at":timezone.now()-timedelta(days=400)},
                       {"event_type":"role.removed"},{"actor_account":self.author},{"subject_account":self.other.account}):
            with self.subTest(fields=fields),self.assertRaises(IntegrityError),transaction.atomic():
                AuditEvent.objects.filter(pk=event.pk).update(**fields)
        AuditEvent.objects.filter(pk=event.pk).update(actor_account=None)
        with self.assertRaises(IntegrityError),transaction.atomic():
            AuditEvent.objects.filter(pk=event.pk).update(actor_account=self.admin)

    def test_database_rejects_recent_deletion(self):
        event = self.event()
        with self.assertRaises(IntegrityError),transaction.atomic():
            event.delete()

    def test_database_metadata_and_attribution_guards_cover_direct_writes(self):
        for fields in ({"metadata":{"role_name":"student","token":"secret"}},
                       {"metadata":[]},{"metadata":{"role_name":"unknown"}},
                       {"event_type":"account.disabled","metadata":{"note":"private"}},
                       {"event_type":"role.removed","actor_account":None},
                       {"subject_account":None}):
            with self.subTest(fields=fields),self.assertRaises(IntegrityError),transaction.atomic():
                self.event(**fields)

    def test_purge_preview_then_execute_preserves_recent_events(self):
        old = self.event(occurred_at=timezone.now()-timedelta(days=367))
        recent = self.event()
        output = StringIO()
        call_command("purge_audit_events",stdout=output)
        self.assertIn("Preview: 1",output.getvalue())
        self.assertTrue(AuditEvent.objects.filter(pk=old.pk).exists())
        output = StringIO()
        call_command("purge_audit_events",execute=True,stdout=output)
        self.assertIn("Purged 1",output.getvalue())
        self.assertFalse(AuditEvent.objects.filter(pk=old.pk).exists())
        self.assertTrue(AuditEvent.objects.filter(pk=recent.pk).exists())


class AuditTransactionTests(TransactionTestCase):
    def test_writer_requires_business_transaction(self):
        with self.assertRaises(RuntimeError):
            _record_event(event_type="role.assigned",metadata={"role_name":"student"})

    def test_guard_migration_reverses_and_reinstalls(self):
        from django.db.migrations.executor import MigrationExecutor
        executor = MigrationExecutor(connection)
        try:
            executor.migrate([("auditing","0001_initial")])
            with connection.cursor() as cursor:
                cursor.execute("SELECT to_regprocedure('audit_event_guard()')")
                self.assertIsNone(cursor.fetchone()[0])
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
        with connection.cursor() as cursor:
            cursor.execute("SELECT to_regprocedure('audit_event_guard()')")
            self.assertIsNotNone(cursor.fetchone()[0])
