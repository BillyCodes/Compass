"""Versioning regressions, database-level type consistency, and draft controls."""
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.utils import timezone

from accounts.models import Account, AccountRole, Role
from reference.models import ContentItem, ContentKind, ContentVersion
from reference.services import create_content_item, create_draft_version, update_draft_version


class ReferenceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.editor=Account.objects.create_user("reference.editor@example.test")
        cls.student=Account.objects.create_user("reference.student@example.test")
        cls.admin=Account.objects.create_user("reference.admin@example.test")
        AccountRole.objects.create(account=cls.editor,role=Role.objects.get(role_name="maintainer"))
        AccountRole.objects.create(account=cls.student,role=Role.objects.get(role_name="student"))
        AccountRole.objects.create(account=cls.admin,role=Role.objects.get(role_name="administrator"))
        cls.item=create_content_item(actor=cls.editor,kind=ContentKind.CAREER)

    def draft(self, **kwargs):
        return create_draft_version(actor=self.editor,item_id=self.item.pk,title="Career draft",body="Draft content",**kwargs)

    def test_all_five_content_kinds_are_supported(self):
        for kind in ContentKind.values:
            item=create_content_item(actor=self.editor,kind=kind)
            self.assertEqual(item.kind,kind)

    def test_students_anonymous_and_disabled_editors_are_rejected(self):
        for actor in (self.student,AnonymousUser()):
            with self.assertRaises(PermissionDenied):
                create_content_item(actor=actor,kind="career")
        self.editor.is_active=False
        with self.assertRaises(PermissionDenied):
            create_draft_version(actor=self.editor,item_id=self.item.pk,title="Denied",body="Denied")

    def test_business_administrator_can_create_draft(self):
        row=create_draft_version(actor=self.admin,item_id=self.item.pk,title="Draft",body="Content")
        self.assertEqual(row.created_by,self.admin)
        self.assertIsNone(row.published_by_id)

    def test_django_staff_flag_does_not_grant_business_editor_access(self):
        self.student.is_staff=True
        self.student.is_superuser=True
        with self.assertRaises(PermissionDenied):
            create_content_item(actor=self.student,kind="course")

    def test_multiple_versions_of_same_item_are_allowed(self):
        one=self.draft()
        two=self.draft()
        self.assertEqual((one.version_no,two.version_no),(1,2))
        self.assertEqual(one.kind,two.kind)
        self.assertEqual(self.item.versions.count(),2)

    def test_duplicate_item_version_number_rejected(self):
        first=self.draft()
        with self.assertRaises(IntegrityError), transaction.atomic():
            ContentVersion.objects.create(item=self.item,kind=self.item.kind,version_no=first.version_no,title="Duplicate",body="Body",created_by=self.editor)

    def test_version_number_and_revision_must_be_positive(self):
        row=self.draft()
        for field in ("version_no","draft_revision"):
            with self.subTest(field=field), self.assertRaises(IntegrityError), transaction.atomic():
                ContentVersion.objects.filter(pk=row.pk).update(**{field:0})

    def test_database_rejects_unknown_kinds_and_statuses(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            ContentItem.objects.create(kind="unknown")
        row=self.draft()
        with self.assertRaises(IntegrityError), transaction.atomic():
            ContentVersion.objects.filter(pk=row.pk).update(status="unknown")

    def test_kind_mismatch_is_rejected_by_model_validation(self):
        row=ContentVersion(item=self.item,kind="course",version_no=1,title="Wrong",body="Wrong",created_by=self.editor)
        with self.assertRaises(ValidationError):
            row.full_clean()

    def test_composite_foreign_key_exists_with_both_columns(self):
        with connection.cursor() as cursor:
            constraints=connection.introspection.get_constraints(cursor,"content_version")
        self.assertEqual(constraints["content_version_item_kind_fk"]["columns"],["item_id","kind"])
        self.assertEqual(constraints["content_version_item_kind_fk"]["foreign_key"][0],"content_item")

    def test_direct_database_write_cannot_mismatch_kind(self):
        row=self.draft()
        with self.assertRaises(IntegrityError), transaction.atomic():
            ContentVersion.objects.filter(pk=row.pk).update(kind="course")
        row.refresh_from_db()
        self.assertEqual(row.kind,"career")

    def test_parent_kind_cannot_change_while_versions_reference_it(self):
        self.draft()
        with self.assertRaises(IntegrityError), transaction.atomic():
            ContentItem.objects.filter(pk=self.item.pk).update(kind="job")

    def test_draft_edits_increment_revision_and_reject_stale_submission(self):
        row=self.draft()
        edited=update_draft_version(actor=self.editor,version_id=row.pk,expected_revision=1,title="Updated",body="Updated body")
        self.assertEqual(edited.draft_revision,2)
        with self.assertRaises(ValidationError):
            update_draft_version(actor=self.editor,version_id=row.pk,expected_revision=1,title="Stale",body="Stale body")
        row.refresh_from_db()
        self.assertEqual(row.title,"Updated")
        self.assertEqual(row.draft_revision,2)

    def test_retired_item_cannot_receive_a_new_version(self):
        self.item.retired_at=timezone.now()
        self.item.save(update_fields=["retired_at"])
        with self.assertRaises(ValidationError):
            self.draft()

    def test_published_status_requires_publisher_and_timestamp(self):
        row=self.draft()
        with self.assertRaises(IntegrityError), transaction.atomic():
            ContentVersion.objects.filter(pk=row.pk).update(status="published")
        with self.assertRaises(IntegrityError), transaction.atomic():
            ContentVersion.objects.filter(pk=row.pk).update(published_at=timezone.now())

    def test_draft_service_cannot_edit_non_draft_content(self):
        row=self.draft()
        # Fixture simulates a later publication workflow; no publication route exists.
        row.status="published"
        row.published_by=self.editor
        row.published_at=timezone.now()
        row.save()
        with self.assertRaises(ValidationError):
            update_draft_version(actor=self.editor,version_id=row.pk,expected_revision=1,title="Forbidden",body="Forbidden")

    def test_empty_title_or_body_is_rejected_without_saving(self):
        for title,body in [("  ","Body"),("Title","  ")]:
            with self.subTest(title=title), self.assertRaises(ValidationError):
                create_draft_version(actor=self.editor,item_id=self.item.pk,title=title,body=body)
        self.assertFalse(ContentVersion.objects.exists())

    def test_item_and_author_with_versions_are_protected(self):
        self.draft()
        with self.assertRaises(ProtectedError):
            self.item.delete()
        with self.assertRaises(ProtectedError):
            self.editor.delete()
