"""Real PostgreSQL constraints plus business-role and student-ownership checks."""
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase

from accounts.models import Account, AccountRole, Role
from accounts.services import create_student
from skills.models import ProficiencyLevel, Skill, StudentSkill
from skills.services import create_skill, list_student_skills, retire_skill, set_student_skill


class SkillTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.a = create_student(email="skill.a@example.test", password=None, display_name="A")
        cls.b = create_student(email="skill.b@example.test", password=None, display_name="B")
        cls.editor = Account.objects.create_user("skills.editor@example.test")
        AccountRole.objects.create(account=cls.editor, role=Role.objects.get(role_name="maintainer"))
        cls.skill = create_skill(actor=cls.editor, skill_name="SQL", category="Database")

    def test_maintainer_can_create_validated_catalog_entry(self):
        skill = create_skill(actor=self.editor, skill_name="  Testing  ", category=" Programming ")
        self.assertEqual(skill.skill_name, "Testing")
        self.assertEqual(skill.category, "Programming")
        self.assertEqual(skill.status, "active")

    def test_catalog_edits_reject_students_anonymous_and_disabled_accounts(self):
        for actor in (self.a.account, AnonymousUser()):
            with self.assertRaises(PermissionDenied):
                create_skill(actor=actor, skill_name="Forbidden")
        self.editor.is_active = False
        with self.assertRaises(PermissionDenied):
            retire_skill(actor=self.editor, skill_id=self.skill.pk)

    def test_django_superuser_is_not_implicitly_a_catalog_editor(self):
        operator = Account.objects.create_superuser("skills.operator@example.test", None)
        with self.assertRaises(PermissionDenied):
            create_skill(actor=operator, skill_name="Forbidden")

    def test_catalog_rejects_empty_and_duplicate_names(self):
        for name in ("  ", "SQL"):
            with self.subTest(name=name), self.assertRaises(ValidationError):
                create_skill(actor=self.editor, skill_name=name)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Skill.objects.create(skill_name="")

    def test_database_rejects_invalid_skill_status(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Skill.objects.filter(pk=self.skill.pk).update(status="unknown")

    def test_all_six_levels_can_be_saved_and_updating_reuses_the_record(self):
        ids=[]
        for value in ProficiencyLevel.values:
            row=set_student_skill(actor=self.a.account, skill_id=self.skill.pk, proficiency_level=value)
            ids.append(row.pk)
            self.assertEqual(row.proficiency_level,value)
        self.assertEqual(len(set(ids)),1)
        self.assertEqual(StudentSkill.objects.filter(student=self.a).count(),1)

    def test_service_rejects_out_of_range_and_non_integer_levels(self):
        for level in (-1, 6, 2.5, True, "3", None):
            with self.subTest(level=level), self.assertRaises(ValidationError):
                set_student_skill(actor=self.a.account, skill_id=self.skill.pk, proficiency_level=level)
        self.assertFalse(StudentSkill.objects.exists())

    def test_database_enforces_level_bounds(self):
        for level in (-1, 6):
            with self.subTest(level=level), self.assertRaises(IntegrityError), transaction.atomic():
                StudentSkill.objects.create(student=self.a, skill=self.skill, proficiency_level=level)

    def test_student_skill_pair_is_unique_in_database(self):
        set_student_skill(actor=self.a.account, skill_id=self.skill.pk, proficiency_level=2)
        with self.assertRaises(IntegrityError), transaction.atomic():
            StudentSkill.objects.create(student=self.a, skill=self.skill, proficiency_level=4)

    def test_student_reads_and_writes_are_owner_scoped(self):
        set_student_skill(actor=self.a.account, skill_id=self.skill.pk, proficiency_level=2)
        set_student_skill(actor=self.b.account, skill_id=self.skill.pk, proficiency_level=4)
        own=list(list_student_skills(actor=self.a.account))
        self.assertEqual(len(own),1)
        self.assertEqual(own[0].student_id,self.a.pk)
        self.assertEqual(own[0].proficiency_level,2)
        self.assertEqual(StudentSkill.objects.get(student=self.b).proficiency_level,4)
        # The write contract never accepts a caller-selected owner.
        with self.assertRaises(TypeError):
            set_student_skill(actor=self.a.account, skill_id=self.skill.pk, proficiency_level=5, student_id=self.b.pk)

    def test_maintainer_without_student_profile_cannot_write_student_skills(self):
        with self.assertRaises(PermissionDenied):
            set_student_skill(actor=self.editor, skill_id=self.skill.pk, proficiency_level=2)

    def test_disabled_student_cannot_read_or_write(self):
        self.a.account.is_active=False
        with self.assertRaises(PermissionDenied):
            list_student_skills(actor=self.a.account)
        with self.assertRaises(PermissionDenied):
            set_student_skill(actor=self.a.account, skill_id=self.skill.pk, proficiency_level=2)

    def test_retirement_preserves_records_but_blocks_new_edits(self):
        row=set_student_skill(actor=self.a.account, skill_id=self.skill.pk, proficiency_level=3)
        retire_skill(actor=self.editor, skill_id=self.skill.pk)
        with self.assertRaises(ValidationError):
            set_student_skill(actor=self.a.account, skill_id=self.skill.pk, proficiency_level=4)
        row.refresh_from_db()
        self.assertEqual(row.proficiency_level,3)
        self.assertEqual(list_student_skills(actor=self.a.account).count(),1)

    def test_used_skill_is_protected_and_student_deletion_removes_private_record(self):
        set_student_skill(actor=self.a.account, skill_id=self.skill.pk, proficiency_level=3)
        with self.assertRaises(ProtectedError):
            self.skill.delete()
        self.a.delete()
        self.assertFalse(StudentSkill.objects.exists())
        self.assertTrue(Skill.objects.filter(pk=self.skill.pk).exists())

    def test_evidence_is_plain_text_and_required_to_be_a_string(self):
        row=set_student_skill(actor=self.a.account, skill_id=self.skill.pk, proficiency_level=2, evidence_text="<b>Self-reported</b>")
        self.assertEqual(row.evidence_text,"<b>Self-reported</b>")
        with self.assertRaises(ValidationError):
            set_student_skill(actor=self.a.account, skill_id=self.skill.pk, proficiency_level=2, evidence_text=None)
