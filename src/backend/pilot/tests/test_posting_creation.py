"""A new posting and its first comparison must succeed or fail together."""
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.urls import reverse

from pilot.models import PostingMatch, StudentPosting, StudentPostingRequirement
from pilot.services import postings
from pilot.tests.test_pilot import PilotBase
from skills.models import StudentSkill


class PostingCreationTests(PilotBase):
    DATA = {
        "title": "Synthetic developer",
        "company": "Sample company",
        "description": (
            "Requirements:\nPython and SQL experience building synthetic demonstration "
            "applications and working with a small project team."
        ),
    }

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        StudentSkill.objects.create(student=cls.a, skill=cls.python, proficiency_level=3)

    def assert_no_posting_records(self):
        self.assertFalse(StudentPosting.objects.exists())
        self.assertFalse(StudentPostingRequirement.objects.exists())
        self.assertFalse(PostingMatch.objects.exists())

    def test_submission_saves_posting_requirements_and_first_result(self):
        response = self.login().post(reverse("pilot:posting-create"), self.DATA)

        match = PostingMatch.objects.get()
        self.assertRedirects(response, reverse("comparisons:detail", args=[match.pk]))
        self.assertEqual(match.student_id, self.a.pk)
        self.assertEqual(match.posting.student_id, self.a.pk)
        self.assertEqual(StudentPosting.objects.count(), 1)
        self.assertSetEqual(
            set(match.posting.requirements.values_list("skill_id", flat=True)),
            {self.python.pk, self.sql.pk},
        )

    def test_validation_failure_returns_populated_form_and_rolls_back(self):
        # Fail after a real result insert to cover rollback of all three tables.
        run_match = postings.run_posting_match

        def fail_after_save(**kwargs):
            run_match(**kwargs)
            raise ValidationError("Comparison could not be completed.")

        with patch.object(postings, "run_posting_match", side_effect=fail_after_save):
            response = self.login().post(reverse("pilot:posting-create"), self.DATA)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Comparison could not be completed.")
        form = response.context["form"]
        self.assertTrue(form.is_bound)
        for field, value in self.DATA.items():
            self.assertEqual(form[field].value(), value)
        self.assert_no_posting_records()

    def test_unexpected_failure_also_rolls_back(self):
        with patch.object(postings, "_recommendations", side_effect=RuntimeError("Unavailable")):
            with self.assertRaisesMessage(RuntimeError, "Unavailable"):
                postings.create_posting_and_match(actor=self.a.account, **self.DATA)

        self.assert_no_posting_records()

    def test_unrecognized_skills_leave_no_records(self):
        with self.assertRaises(ValidationError):
            postings.create_posting_and_match(
                actor=self.a.account, **{**self.DATA, "description": "No catalog skills here."})

        self.assert_no_posting_records()

    def test_no_reported_proficiency_leaves_no_posting(self):
        StudentSkill.objects.filter(student=self.a).delete()

        response = self.login().post(reverse("pilot:posting-create"), self.DATA)

        self.assertContains(response, "Report at least one relevant proficiency")
        self.assert_no_posting_records()

    def test_failed_rerun_preserves_existing_posting_and_result(self):
        first = postings.create_posting_and_match(actor=self.a.account, **self.DATA)
        with patch.object(postings, "calculate", side_effect=ValidationError("Try again later.")):
            response = self.login().post(reverse("pilot:posting-run", args=[first.posting_id]))

        self.assertRedirects(response, reverse("comparisons:compare"))
        self.assertEqual(list(StudentPosting.objects.values_list("pk", flat=True)), [first.posting_id])
        self.assertEqual(list(PostingMatch.objects.values_list("pk", flat=True)), [first.pk])
        self.assertEqual(StudentPostingRequirement.objects.count(), 2)
