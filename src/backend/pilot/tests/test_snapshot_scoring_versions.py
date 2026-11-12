"""A category formula change must not masquerade as student progress."""
from datetime import timedelta

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from comparisons.tests.factories import setup_actors
from pilot.models import ProgressSnapshot
from pilot.services import skillprint
from skills.services import set_student_skill


class SnapshotScoringVersionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        setup_actors(cls)
        cls.python.category = "Programming"
        cls.python.save(update_fields=["category"])
        cls.sql.category = "Database"
        cls.sql.save(update_fields=["category"])

    def setUp(self):
        self.client.force_login(self.student.account)
        set_student_skill(actor=self.student.account, skill_id=self.python.pk, proficiency_level=4)

    def legacy(self, days=2, score=26.7):
        return ProgressSnapshot.objects.create(
            student=self.student, label="Old formula", skills={str(self.python.pk): 4},
            categories={"programming": score}, scoring_version=ProgressSnapshot.LEGACY_SCORING,
            created_at=timezone.now() - timedelta(days=days))

    def test_new_saves_use_current_formula_and_keep_category_aliases(self):
        set_student_skill(actor=self.student.account, skill_id=self.sql.pk, proficiency_level=2)
        snap = skillprint.save_snapshot(actor=self.student.account)
        self.assertEqual(snap.scoring_version, ProgressSnapshot.CURRENT_SCORING)
        self.assertEqual(snap.categories["programming"], 80)
        self.assertEqual(snap.categories["data"], 40)
        self.assertTrue(skillprint.snapshot_is_current(snap))

    def test_legacy_snapshots_are_not_overlaid_on_current_charts(self):
        legacy = self.legacy()
        for route in ("core:dashboard", "skills:skillprint", "comparisons:journey"):
            with self.subTest(route=route):
                response = self.client.get(reverse(route))
                self.assertEqual(response.status_code, 200)
                self.assertNotIn('class="radar-prev"', response.context["radar"])
                self.assertContains(response, "earlier scoring method")
        response = self.client.get(reverse("comparisons:journey"))
        self.assertEqual(response.context["timeline"][0]["snap"].pk, legacy.pk)
        self.assertTrue(response.context["timeline"][0]["legacy_score"])
        legacy.refresh_from_db()
        self.assertEqual(legacy.categories, {"programming": 26.7})

    def test_current_overlays_and_deltas_skip_the_formula_boundary(self):
        self.legacy()
        first = skillprint.save_snapshot(actor=self.student.account, label="Current baseline")
        set_student_skill(actor=self.student.account, skill_id=self.python.pk, proficiency_level=5)
        second = skillprint.save_snapshot(actor=self.student.account, label="Improved")
        response = self.client.get(reverse("comparisons:journey"))
        timeline = response.context["timeline"]
        self.assertEqual([row["snap"].pk for row in timeline[:2]], [second.pk, first.pk])
        self.assertEqual(timeline[0]["changes"], [("Programming", 20)])
        self.assertFalse(timeline[0]["scoring_changed"])
        self.assertEqual(timeline[1]["changes"], [])
        self.assertTrue(timeline[1]["scoring_changed"])
        self.assertEqual(response.context["oldest"].pk, first.pk)
        self.assertContains(response, "score differences are not compared")
        for route in ("core:dashboard", "skills:skillprint", "comparisons:journey"):
            response = self.client.get(reverse(route))
            self.assertIn('class="radar-prev"', response.context["radar"])

    def test_formula_boundary_across_pagination_is_not_compared(self):
        self.legacy()
        for n in range(20):
            skillprint.save_snapshot(actor=self.student.account, label=f"Current {n}")
        response = self.client.get(reverse("comparisons:journey"))
        boundary = response.context["timeline"][-1]
        self.assertTrue(boundary["scoring_changed"])
        self.assertEqual(boundary["changes"], [])
        page_two = self.client.get(reverse("comparisons:journey"), {"snapshots_page": 2})
        self.assertTrue(page_two.context["timeline"][0]["legacy_score"])

    def test_legacy_history_still_compares_like_for_like_and_is_owned(self):
        self.legacy(days=3, score=20)
        self.legacy(days=2, score=26.7)
        ProgressSnapshot.objects.create(student=self.other, skills={}, categories={"programming": 100},
                                        scoring_version=ProgressSnapshot.CURRENT_SCORING)
        response = self.client.get(reverse("comparisons:journey"))
        self.assertEqual(response.context["timeline"][0]["changes"], [("Programming", 6.7)])
        self.assertEqual(len(response.context["timeline"]), 2)
        self.assertIsNone(response.context["oldest"])

    def test_home_describes_direct_publication_and_retains_demo_disclosure(self):
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, "Content maintainers publish career profiles and Field Notes with supporting sources.")
        self.assertContains(response, "curated public sources, original personal reflections and labeled synthetic demonstration content")
        self.assertNotContains(response, "reviewed by a second person")


class SnapshotScoringMigrationTests(TransactionTestCase):
    def test_existing_scores_are_preserved_and_marked_legacy(self):
        setup_actors(self)
        executor = MigrationExecutor(connection)
        try:
            executor.migrate([("pilot", "0002_frozen_posting_recommendations")])
            old_apps = executor.loader.project_state([("pilot", "0002_frozen_posting_recommendations")]).apps
            old_snapshot = old_apps.get_model("pilot", "ProgressSnapshot")
            legacy = old_snapshot.objects.create(student_id=self.student.pk,
                skills={str(self.python.pk): 4}, categories={"programming": 26.7})
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
        saved = ProgressSnapshot.objects.get(pk=legacy.pk)
        self.assertEqual(saved.scoring_version, ProgressSnapshot.LEGACY_SCORING)
        self.assertEqual(saved.categories, {"programming": 26.7})
        self.assertEqual(saved.skills, {str(self.python.pk): 4})
        current = skillprint.save_snapshot(actor=self.student.account)
        self.assertEqual(current.scoring_version, ProgressSnapshot.CURRENT_SCORING)
