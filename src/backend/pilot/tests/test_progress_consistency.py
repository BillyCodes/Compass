"""Dashboard summaries expose unknowns; snapshots capture one set of inputs."""
from django.core.exceptions import PermissionDenied
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from comparisons.tests.factories import setup_actors, target
from pilot.services import presenter, skillprint
from skills.models import StudentSkill
from skills.services import set_student_skill


class ProgressConsistencyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        setup_actors(cls)
        cls.python.category = "Programming"
        cls.python.save(update_fields=["category"])
        cls.sql.category = "Database"
        cls.sql.save(update_fields=["category"])

    def set_level(self, skill, level):
        return set_student_skill(actor=self.student.account, skill_id=skill.pk, proficiency_level=level)

    def test_snapshot_uses_same_rows_when_proficiency_changes_after_read(self):
        self.set_level(self.python, 1)
        changed = False

        def edit_after_read(execute, sql, params, many, context):
            nonlocal changed
            result = execute(sql, params, many, context)
            if not changed and sql.lstrip().startswith("SELECT") and 'FROM "student_skill"' in sql:
                changed = True
                # Simulate a proficiency edit after the first result is captured,
                # before any second query could read a different input state.
                self.set_level(self.python, 5)
            return result

        with connection.execute_wrapper(edit_after_read):
            snapshot = skillprint.save_snapshot(actor=self.student.account)
        self.assertTrue(changed)
        self.assertEqual(StudentSkill.objects.get(student=self.student, skill=self.python).proficiency_level, 5)
        self.assertEqual(snapshot.skills[str(self.python.pk)], 1)
        self.assertEqual(snapshot.categories["programming"], skillprint.category_scores({"programming": [1]})["programming"])

    def test_snapshot_reads_inputs_once_and_preserves_zero_and_ownership(self):
        self.set_level(self.sql, 0)
        set_student_skill(actor=self.other.account, skill_id=self.python.pk, proficiency_level=5)
        with CaptureQueriesContext(connection) as queries:
            snapshot = skillprint.save_snapshot(actor=self.student.account)
        reads = [query for query in queries if query["sql"].lstrip().startswith("SELECT") and 'FROM "student_skill"' in query["sql"]]
        self.assertEqual(len(reads), 1)
        self.assertEqual(snapshot.skills, {str(self.sql.pk): 0})
        self.assertNotIn(str(self.python.pk), snapshot.skills)
        self.assertTrue(all(value == 0 for value in snapshot.categories.values()))

    def test_empty_snapshot_is_consistent_and_requires_student_role(self):
        snapshot = skillprint.save_snapshot(actor=self.student.account)
        self.assertEqual(snapshot.skills, {})
        self.assertTrue(all(value == 0 for value in snapshot.categories.values()))
        with self.assertRaises(PermissionDenied):
            skillprint.save_snapshot(actor=self.author)

    def test_dashboard_marks_high_scoring_partial_job_match_provisional(self):
        version = target(self, "job", requirements=[(self.python, 4, "99", True), (self.sql, 3, "1", False)])
        self.set_level(self.python, 4)
        self.client.force_login(self.student.account)
        response = self.client.get(reverse("core:dashboard"))
        card = next(row for row in response.context["matches"] if row["pk"] == version.pk)
        self.assertEqual(str(card["score"]), "99.00")
        self.assertTrue(card["is_provisional"])
        self.assertEqual((card["reported_count"], card["relevant_count"]), (1, 2))
        self.assertEqual(card["mandatory_status"], "met")
        self.assertContains(response, "Provisional")
        self.assertContains(response, "1 of 2 relevant skills reported. Mandatory requirements: Met.")
        self.set_level(self.sql, 0)
        complete = self.client.get(reverse("core:dashboard"))
        self.assertContains(complete, "Inputs complete")
        self.assertContains(complete, "2 of 2 relevant skills reported.")
        self.assertNotContains(complete, "Provisional")

    def test_live_cards_preserve_unknown_mandatory_status(self):
        version = target(self, "job")
        self.set_level(self.sql, 3)
        card = next(row for row in presenter.live_job_matches({self.sql.pk: 3}) if row["pk"] == version.pk)
        self.assertEqual(card["mandatory_status"], "undetermined")
        self.assertEqual(card["mandatory_label"], "Undetermined")
        self.assertTrue(card["is_provisional"])
