"""Private course selection uses stable, published course identities."""
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.utils import timezone

from accounts.models import Account, AccountRole, Role
from accounts.services import create_student
from reference.models import ContentItem
from reference.services import create_content_item, create_draft_version, retire_content_version
from reference.tests.factories import publish_complete_version
from skills.models import StudentCourse, StudentSkill
from skills.services import list_student_courses, remove_student_course, select_student_course


class StudentCourseTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.a = create_student(email="course.a@example.test",password=None,display_name="Course A")
        cls.b = create_student(email="course.b@example.test",password=None,display_name="Course B")
        cls.author = Account.objects.create_user("course.author@example.test")
        cls.reviewer = Account.objects.create_user("course.reviewer@example.test")
        for actor in (cls.author,cls.reviewer):
            AccountRole.objects.create(account=actor,role=Role.objects.get(role_name="maintainer"))
        cls.item = create_content_item(actor=cls.author,kind="course")
        version = create_draft_version(actor=cls.author,item_id=cls.item.pk,title="Sample course",body="Synthetic coursework")
        cls.version = publish_complete_version(version,cls.author,cls.reviewer)

    def select(self, actor=None, **extra):
        return select_student_course(actor=actor or self.a.account,course_item_id=self.item.pk,**extra)

    def test_selecting_a_published_course_is_idempotent(self):
        first = self.select()
        second = self.select()
        self.assertEqual(first.pk,second.pk)
        self.assertEqual(first.student_id,self.a.pk)
        self.assertEqual(first.course_kind,"course")
        self.assertEqual(StudentCourse.objects.count(),1)

    def test_database_rejects_duplicate_student_course_pair(self):
        self.select()
        with self.assertRaises(IntegrityError), transaction.atomic():
            StudentCourse.objects.create(student=self.a,course_item=self.item)

    def test_only_owner_reads_and_removes_their_selection(self):
        self.select()
        self.select(actor=self.b.account)
        own = list(list_student_courses(actor=self.a.account))
        self.assertEqual(len(own),1)
        self.assertEqual(own[0].student_id,self.a.pk)
        self.assertTrue(remove_student_course(actor=self.a.account,course_item_id=self.item.pk))
        self.assertEqual(list_student_courses(actor=self.b.account).count(),1)
        self.assertFalse(remove_student_course(actor=self.a.account,course_item_id=self.item.pk))

    def test_caller_cannot_select_for_another_student(self):
        with self.assertRaises(TypeError):
            self.select(student_id=self.b.pk)
        self.assertFalse(StudentCourse.objects.exists())

    def test_anonymous_maintainer_and_disabled_students_cannot_select(self):
        for actor in (AnonymousUser(),self.author):
            with self.assertRaises(PermissionDenied):
                select_student_course(actor=actor,course_item_id=self.item.pk)
        self.a.account.is_active = False
        with self.assertRaises(PermissionDenied):
            self.select()
        with self.assertRaises(PermissionDenied):
            list_student_courses(actor=self.a.account)
        with self.assertRaises(PermissionDenied):
            remove_student_course(actor=self.a.account,course_item_id=self.item.pk)

    def test_non_course_and_draft_only_items_cannot_be_selected(self):
        for kind in ("job","course"):
            item = create_content_item(actor=self.author,kind=kind)
            with self.assertRaises(ValidationError):
                select_student_course(actor=self.a.account,course_item_id=item.pk)
        self.assertFalse(StudentCourse.objects.exists())

    def test_item_retirement_blocks_new_selections_but_keeps_existing_history(self):
        self.select()
        ContentItem.objects.filter(pk=self.item.pk).update(retired_at=timezone.now())
        with self.assertRaises(ValidationError):
            self.select(actor=self.b.account)
        self.assertEqual(list_student_courses(actor=self.a.account).count(),1)

    def test_retiring_last_published_version_blocks_new_selections(self):
        retire_content_version(actor=self.author,version_id=self.version.pk)
        with self.assertRaises(ValidationError):
            self.select()

    def test_course_selection_does_not_change_proficiency(self):
        self.select()
        self.assertFalse(StudentSkill.objects.filter(student=self.a).exists())

    def test_typed_foreign_key_rejects_non_course_target_in_direct_write(self):
        job = ContentItem.objects.create(kind="job")
        with self.assertRaises(IntegrityError), transaction.atomic():
            StudentCourse.objects.create(student=self.a,course_item=job)
        with self.assertRaises(IntegrityError), transaction.atomic():
            StudentCourse.objects.create(student=self.a,course_item=job,course_kind="job")
        with connection.cursor() as cursor:
            constraints = connection.introspection.get_constraints(cursor,"student_course")
        self.assertEqual(constraints["student_course_item_kind_fk"]["columns"],["course_item_id","course_kind"])

    def test_selection_remains_on_same_item_when_successor_is_created(self):
        row = self.select()
        successor = create_draft_version(actor=self.author,item_id=self.item.pk,title="Revised course",body="New material")
        self.assertEqual(successor.version_no,2)
        row.refresh_from_db()
        self.assertEqual(row.course_item_id,self.item.pk)
        self.assertEqual(StudentCourse.objects.count(),1)

    def test_student_deletion_removes_only_private_selection(self):
        self.select()
        self.a.delete()
        self.assertFalse(StudentCourse.objects.exists())
        self.assertTrue(ContentItem.objects.filter(pk=self.item.pk).exists())

    def test_selected_course_identity_cannot_be_deleted(self):
        self.select()
        with self.assertRaises(ProtectedError):
            self.item.delete()
