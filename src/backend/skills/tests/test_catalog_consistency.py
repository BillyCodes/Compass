"""Course eligibility and paginated Skillprints agree across student screens."""
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from comparisons.tests.factories import approve, learning, setup_actors
from pilot.services.presenter import reference_available
from reference.models import ContentItem, ContentSkill
from reference.selectors import latest_available
from reference.services import create_successor_draft, retire_content_version, set_skill_mapping
from skills.forms import CourseForm
from skills.models import Skill, StudentCourse, StudentSkill
from skills.services import retire_skill, select_student_course


class CatalogConsistencyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        setup_actors(cls)
        cls.course = learning(cls, cls.python)

    def setUp(self):
        self.client.force_login(self.student.account)

    def card(self):
        return self.client.get(reverse("skills:skillprint")).context["courses"][0]

    def test_withdrawn_successor_uses_older_available_edition(self):
        select_student_course(actor=self.student.account, course_item_id=self.course.item_id)
        new = approve(self, create_successor_draft(actor=self.author, version_id=self.course.pk))
        self.assertEqual(self.card()["version"].pk, new.pk)
        retire_content_version(actor=self.author, version_id=new.pk)
        card = self.card()
        self.assertEqual(card["version"].pk, self.course.pk)
        self.assertTrue(card["available"])
        self.assertContains(self.client.get(reverse("reference:learning", args=[self.course.pk])), self.course.title)
        self.assertTrue(CourseForm().fields["course"].queryset.filter(pk=self.course.pk).exists())

    def test_retired_mapping_blocks_selection_but_preserves_private_history(self):
        select_student_course(actor=self.student.account, course_item_id=self.course.item_id)
        retire_skill(actor=self.author, skill_id=self.python.pk)
        self.assertFalse(CourseForm().fields["course"].queryset.filter(pk=self.course.pk).exists())
        with self.assertRaises(ValidationError):
            select_student_course(actor=self.other.account, course_item_id=self.course.item_id)
        self.assertEqual(self.client.get(reverse("reference:learning", args=[self.course.pk])).status_code, 404)
        self.assertEqual(reference_available([self.course.pk]), set())
        self.assertFalse(self.card()["available"])
        self.assertEqual(self.card()["version"].pk, self.course.pk)
        self.assertEqual(StudentCourse.objects.filter(student=self.student).count(), 1)
        self.assertContains(self.client.get(reverse("skills:skillprint")), "no longer available")

    def test_newer_published_ineligible_edition_does_not_expose_older_one(self):
        select_student_course(actor=self.student.account, course_item_id=self.course.item_id)
        new = create_successor_draft(actor=self.author, version_id=self.course.pk)
        ContentSkill.objects.filter(version=new).delete()
        new.refresh_from_db()
        set_skill_mapping(actor=self.author, version_id=new.pk, expected_revision=new.draft_revision,
                          skill_id=self.sql.pk, coverage_level=4)
        new = approve(self, new)
        retire_skill(actor=self.author, skill_id=self.sql.pk)
        self.assertFalse(latest_available("course").filter(item_id=self.course.item_id).exists())
        with self.assertRaises(ValidationError):
            select_student_course(actor=self.other.account, course_item_id=self.course.item_id)
        self.assertFalse(self.card()["available"])
        # An older saved recommendation's exact edition remains usable.
        self.assertEqual(reference_available([self.course.pk, new.pk]), {self.course.pk})

    def test_retired_item_and_last_withdrawn_edition_keep_unavailable_history(self):
        select_student_course(actor=self.student.account, course_item_id=self.course.item_id)
        ContentItem.objects.filter(pk=self.course.item_id).update(retired_at=timezone.now())
        self.assertFalse(self.card()["available"])
        self.assertFalse(CourseForm().fields["course"].queryset.filter(pk=self.course.pk).exists())
        self.assertEqual(self.client.get(reverse("reference:learning", args=[self.course.pk])).status_code, 404)
        ContentItem.objects.filter(pk=self.course.item_id).update(retired_at=None)
        retire_content_version(actor=self.author, version_id=self.course.pk)
        self.assertFalse(self.card()["available"])
        self.assertEqual(self.card()["version"].status, "retired")

    def test_paginated_category_emptiness_does_not_deny_reported_skills(self):
        self.python.category = "Programming"
        self.python.save(update_fields=["category"])
        self.sql.category = "Database"
        self.sql.save(update_fields=["category"])
        skills = [self.python, self.sql]
        skills += [Skill.objects.create(skill_name=f"Synthetic {n:02}", category="Programming") for n in range(19)]
        for skill in skills:
            StudentSkill.objects.create(student=self.student, skill=skill, proficiency_level=4)
        response = self.client.get(reverse("skills:skillprint"), {"skills_page": 2})
        data = next(group for group in response.context["groups"] if group[0] == "data")
        self.assertEqual(data[2], 80)
        self.assertEqual(data[3], [])
        self.assertContains(response, "No data skills on this page.")
        self.assertNotContains(response, "No data skills yet.")

    def test_unpaginated_empty_category_still_uses_original_message(self):
        self.assertContains(self.client.get(reverse("skills:skillprint")), "No data skills yet.")
