"""Cross-branch contracts: existing UUID accounts can use launch features."""
import json

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from accounts.models import Account, Student
from accounts.services import create_student
from core.models import Skill, StudentSkill


class IntegrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.student = create_student(
            email="existing@example.test", password="Existing-Compass-2026!",
            display_name="Existing Student", graduation_year=2027,
        )
        Skill.objects.create(skill_id="python", name="Python", category="programming")

    def setUp(self):
        cache.clear()

    def test_existing_account_uses_launch_login_and_uuid_relations(self):
        response = self.client.post("/login/", {
            "email": "EXISTING@EXAMPLE.TEST", "password": "Existing-Compass-2026!",
        })
        self.assertRedirects(response, "/dashboard/")
        self.client.post("/skillprint/", {"skill-skill": "python", "skill-level": 3})
        self.assertEqual(StudentSkill.objects.get().student_id, self.student.pk)
        self.assertEqual(Account.objects.count(), 1)
        self.assertEqual(Student.objects.count(), 1)

    def test_legacy_login_session_opens_new_dashboard(self):
        self.client.post(reverse("accounts:login"), {
            "username": "existing@example.test", "password": "Existing-Compass-2026!",
        })
        self.assertContains(self.client.get("/dashboard/"), "Existing")
        self.assertContains(self.client.get("/profile/"), "existing@example.test")

    def test_api_profile_name_maps_to_existing_display_name(self):
        self.client.force_login(self.student.account)
        response = self.client.patch("/api/me", json.dumps({"name": "Updated Name"}), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["name"], "Updated Name")
        self.student.refresh_from_db()
        self.assertEqual(self.student.display_name, "Updated Name")
        self.assertEqual(self.student.graduation_year, 2027)

    def test_profile_form_updates_same_student_without_privilege_changes(self):
        self.client.force_login(self.student.account)
        response = self.client.post("/profile/", {
            "display_name": "New Name", "major": "CS", "career_interests": "Cloud",
            "account": "forged", "graduation_year": 1999, "is_staff": True,
        })
        self.assertRedirects(response, "/profile/")
        self.student.refresh_from_db()
        self.assertEqual(self.student.display_name, "New Name")
        self.assertEqual(self.student.graduation_year, 2027)
        self.assertFalse(self.student.account.is_staff)

    def test_registration_rejects_case_variant_of_existing_account(self):
        response = self.client.post("/api/register", json.dumps({
            "name": "Duplicate", "email": "EXISTING@EXAMPLE.TEST", "password": "Other-Compass-2026!",
        }), content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Account.objects.count(), 1)

    def test_launch_login_rejects_external_redirects(self):
        for target in ["https://example.org/", "//example.org/", "/\\example.org/"]:
            self.client.logout()
            response = self.client.post("/login/", {
                "email": "existing@example.test", "password": "Existing-Compass-2026!",
            }, QUERY_STRING="next=" + target)
            self.assertRedirects(response, "/dashboard/")

    def test_maintainer_without_student_cannot_use_student_api(self):
        account = Account.objects.create_user("maintainer@example.test", "Example-Pass-2026!")
        self.client.force_login(account)
        self.assertEqual(self.client.get("/api/me").status_code, 403)
        self.assertEqual(self.client.get(reverse("accounts:profile")).status_code, 200)
