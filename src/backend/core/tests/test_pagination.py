"""Pagination preserves filters, ownership, edition identity, and saved ranks."""
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from comparisons.services import create_comparison, list_matches
from comparisons.tests.factories import approve, draft, learning, setup_actors, target
from reference.selectors import latest_available
from pilot.services.presenter import note_versions
from skills.models import Skill
from skills.services import select_student_course, set_student_skill


class PaginationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        setup_actors(cls)
        cls.careers = [target(cls) for _ in range(3)]
        cls.jobs = [target(cls, "job") for _ in range(3)]
        cls.notes = [approve(cls, draft(cls, "insight")) for _ in range(3)]
        cls.courses = [learning(cls, cls.python) for _ in range(3)]
        # A successor must replace its older edition, including across pages.
        cls.latest_course = learning(cls, cls.python, item=cls.courses[0].item)
        cls.catalog = [Skill.objects.create(skill_name=f"Paged {i:02}", category="Data & systems") for i in range(5)]
        for skill in (cls.python, cls.sql, cls.catalog[0]):
            set_student_skill(actor=cls.student.account, skill_id=skill.pk, proficiency_level=1)
        for course in cls.courses:
            select_student_course(actor=cls.student.account, course_item_id=course.item_id)
        cls.matches = [create_comparison(actor=cls.student.account, target_version_id=cls.careers[0].pk) for _ in range(3)]
        set_student_skill(actor=cls.other.account, skill_id=cls.python.pk, proficiency_level=1)
        cls.private_match = create_comparison(actor=cls.other.account, target_version_id=cls.careers[0].pk)

    def setUp(self):
        self.client.force_login(self.student.account)
        page_size = patch("core.pagination.PAGE_SIZE", 2)
        page_size.start()
        self.addCleanup(page_size.stop)

    def test_history_pages_preserve_order_and_ownership(self):
        expected = list(list_matches(actor=self.student.account).values_list("pk", flat=True))
        seen = []
        for number, count in ((1, 2), (2, 1)):
            response = self.client.get(reverse("comparisons:journey"), {"page": number})
            page = response.context["results"]
            self.assertEqual(page.paginator.count, 3)
            self.assertEqual(len(page), count)
            seen.extend(result.pk for result in page)
            self.assertIn("no-store", response.headers["Cache-Control"])
            self.assertNotContains(response, reverse("comparisons:detail", args=[self.private_match.pk]))
        self.assertEqual(seen, expected)

    def test_explorer_preserves_encoded_filters_and_resets_on_search(self):
        url = reverse("skills:explorer")
        filters = {"q": "Paged", "category": "Data & systems"}
        seen = []
        for number in (1, 2, 3):
            response = self.client.get(url, {**filters, "page": number})
            page = response.context["skills"]
            self.assertEqual(page.paginator.count, 5)
            seen.extend(skill.pk for skill in page)
        self.assertEqual(seen, [skill.pk for skill in self.catalog])
        response = self.client.get(url, filters)
        self.assertContains(response, 'href="?q=Paged&amp;category=Data+%26+systems&amp;page=2"')
        # The GET search form has no hidden page number, so a new search starts at 1.
        self.assertNotContains(response, 'name="page"')

    def test_career_and_job_pages_are_independent(self):
        response = self.client.get(reverse("comparisons:compare"), {"careers_page": 2, "jobs_page": 1})
        self.assertEqual(len(response.context["careers"]), 1)
        self.assertEqual(len(response.context["jobs"]), 2)
        self.assertEqual(response.context["careers"].number, 2)
        self.assertContains(response, 'href="?careers_page=2&amp;jobs_page=2"')
        for kind, key, parameter in (("career", "careers", "careers_page"), ("job", "jobs", "jobs_page")):
            seen = []
            for number in (1, 2):
                page = self.client.get(reverse("comparisons:compare"), {parameter: number}).context[key]
                seen.extend(version.pk for version in page)
            self.assertEqual(seen, list(latest_available(kind).values_list("pk", flat=True)))

    def test_field_notes_are_paged(self):
        seen = []
        for number in (1, 2):
            response = self.client.get(reverse("reference:notes"), {"page": number})
            page = response.context["notes"]
            self.assertEqual(page.paginator.count, 3)
            self.assertLessEqual(len(page), 2)
            seen.extend(version.pk for version in page)
        self.assertEqual(seen, list(note_versions().values_list("pk", flat=True)))

    def test_skillprint_lists_have_independent_pages_and_latest_courses(self):
        response = self.client.get(reverse("skills:skillprint"), {"skills_page": 2, "courses_page": 1})
        self.assertEqual(len(response.context["skill_page"]), 1)
        self.assertEqual(sum(len(records) for _, _, _, records in response.context["groups"]), 1)
        self.assertEqual(len(response.context["course_page"]), 2)
        self.assertContains(response, 'href="?skills_page=2&amp;courses_page=2"')
        editions = []
        for number in (1, 2):
            response = self.client.get(reverse("skills:skillprint"), {"courses_page": number})
            editions.extend(course["version"].pk for course in response.context["courses"])
        self.assertCountEqual(editions, [self.latest_course.pk, self.courses[1].pk, self.courses[2].pk])

    def test_recommendation_pages_keep_saved_ranks(self):
        match = self.matches[0]
        expected = list(match.recommendations.values_list("resource_version_id", flat=True))
        seen, ranks = [], []
        for number in (1, 2):
            response = self.client.get(reverse("comparisons:detail", args=[match.pk]), {"page": number})
            self.assertEqual(response.context["recommendation_page"].paginator.count, 3)
            for suggestion in response.context["recommendations"]:
                seen.append(suggestion["record"].resource_version_id)
                ranks.append(suggestion["record"].priority_rank)
        self.assertEqual(seen, expected)
        self.assertEqual(ranks, [1, 2, 3])

    def test_invalid_pages_and_empty_lists_render_safely(self):
        for value, expected in (("invalid", 1), ("0", 2), ("-1", 2), ("99999", 2)):
            response = self.client.get(reverse("comparisons:journey"), {"page": value})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.context["results"].number, expected)
        response = self.client.get(reverse("skills:explorer"), {"q": "no matching skill", "page": 999})
        self.assertEqual(response.context["skills"].paginator.count, 0)
        self.assertContains(response, "No skills match")
        self.assertNotContains(response, 'aria-label="Skills pagination"')
