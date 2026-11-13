"""Pilot features: resume import, pasted postings, snapshots, API, ownership."""
import json

from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import Account, AccountRole, Role
from accounts.services import create_student
from pilot.models import FieldNoteProfile, PostingMatch, ProgressSnapshot, StudentPosting
from pilot.services import postings, resume, skillprint
from pilot.services.skill_matcher import find_skills
from skills.models import Skill, StudentSkill
from skills.services import create_skill

PASSWORD = "correct-horse-battery-9"


class PilotBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.a = create_student(email="pilot.a@example.test", password=PASSWORD, display_name="A")
        cls.b = create_student(email="pilot.b@example.test", password=PASSWORD, display_name="B")
        cls.editor = Account.objects.create_user("pilot.editor@example.test")
        AccountRole.objects.create(account=cls.editor, role=Role.objects.get(role_name="maintainer"))
        cls.python = create_skill(actor=cls.editor, skill_name="Python", category="Programming")
        cls.sql = create_skill(actor=cls.editor, skill_name="SQL", category="Database")
        cls.java = create_skill(actor=cls.editor, skill_name="Java", category="Programming")
        cls.js = create_skill(actor=cls.editor, skill_name="JavaScript", category="Programming")

    def login(self, email="pilot.a@example.test"):
        client = Client()
        self.assertTrue(client.login(username=email, password=PASSWORD))
        return client


class MatcherTests(PilotBase):
    def test_java_does_not_match_inside_javascript(self):
        names = {h.skill.skill_name for h in find_skills("Built apps in JavaScript.").values()}
        self.assertIn("JavaScript", names)
        self.assertNotIn("Java", names)


class ResumeTests(PilotBase):
    def upload(self, body=b"Experienced software developer with Python and SQL across several projects.", name="cv.txt"):
        return SimpleUploadedFile(name, body, content_type="text/plain")

    def test_import_detects_and_applies_only_detected_skills(self):
        imp = resume.create_import(actor=self.a.account, uploaded=self.upload())
        ids = {d["skill_id"] for d in imp.detected}
        self.assertEqual(ids, {str(self.python.pk), str(self.sql.pk)})
        n = resume.apply_import(actor=self.a.account, import_id=imp.pk, choices={
            str(self.python.pk): 3, str(self.java.pk): 4, str(self.sql.pk): 9})
        self.assertEqual(n, 1)  # undetected skill and out-of-range level are ignored
        self.assertEqual(StudentSkill.objects.get(student=self.a, skill=self.python).proficiency_level, 3)
        self.assertFalse(StudentSkill.objects.filter(student=self.a, skill=self.java).exists())
        self.assertTrue(ProgressSnapshot.objects.filter(student=self.a).exists())

    def test_resume_text_is_not_stored(self):
        imp = resume.create_import(actor=self.a.account, uploaded=self.upload(b"Python developer for several years on many projects. secret-token-123"))
        self.assertNotIn("secret-token-123", json.dumps(imp.detected))

    def test_other_student_cannot_read_or_apply_import(self):
        imp = resume.create_import(actor=self.a.account, uploaded=self.upload())
        with self.assertRaises(ObjectDoesNotExist):
            resume.get_import(actor=self.b.account, import_id=imp.pk)
        with self.assertRaises(ObjectDoesNotExist):
            resume.apply_import(actor=self.b.account, import_id=imp.pk, choices={str(self.python.pk): 3})
        self.assertEqual(self.client.get(reverse("pilot:resume-review", args=[imp.pk])).status_code, 302)
        self.assertEqual(self.login("pilot.b@example.test").get(reverse("pilot:resume-review", args=[imp.pk])).status_code, 404)

    def test_rejects_bad_type_and_oversize(self):
        with self.assertRaises(resume.ResumeError):
            resume.create_import(actor=self.a.account, uploaded=self.upload(b"MZ\x90\x00", "cv.pdf"))
        with self.assertRaises(resume.ResumeError):
            resume.create_import(actor=self.a.account, uploaded=self.upload(b"a" * (2 * 1024 * 1024 + 1)))

    def test_upload_requires_login(self):
        self.assertEqual(self.client.post(reverse("pilot:resume-upload")).status_code, 302)


class PostingTests(PilotBase):
    TEXT = "Requirements:\n- Python\n- SQL\nNice to have:\n- Java\n"

    def test_parse_marks_required_and_preferred(self):
        reqs = {r["skill"].skill_name: r for r in postings.parse_requirements(self.TEXT)}
        self.assertTrue(reqs["Python"]["mandatory"])
        self.assertFalse(reqs["Java"]["mandatory"])

    def test_match_is_frozen_and_owned(self):
        StudentSkill.objects.create(student=self.a, skill=self.python, proficiency_level=3)
        posting = postings.create_posting(actor=self.a.account, title="Dev", company="Acme", description=self.TEXT)
        match = postings.run_posting_match(actor=self.a.account, posting_id=posting.pk)
        self.assertEqual(match.alg_version, "weighted_skill_match_v1")
        self.assertTrue(0 <= match.score <= 100)
        with self.assertRaises(ObjectDoesNotExist):
            postings.run_posting_match(actor=self.b.account, posting_id=posting.pk)
        with self.assertRaises(ObjectDoesNotExist):
            postings.get_posting_match(actor=self.b.account, match_id=match.pk)
        self.assertEqual(self.login("pilot.b@example.test").post(reverse("pilot:posting-run", args=[posting.pk])).status_code, 404)

    def test_db_constraint_rejects_bad_score(self):
        StudentSkill.objects.create(student=self.a, skill=self.python, proficiency_level=3)
        posting = postings.create_posting(actor=self.a.account, title="Dev", company="Acme", description=self.TEXT)
        match = postings.run_posting_match(actor=self.a.account, posting_id=posting.pk)
        with self.assertRaises(IntegrityError), transaction.atomic():
            PostingMatch.objects.filter(pk=match.pk).update(score=101)


class CategoryScoreTests(TestCase):
    def test_single_skill_maps_linearly_to_100(self):
        for level, expected in enumerate([0, 20, 40, 60, 80, 100]):
            self.assertEqual(skillprint.category_scores({"programming": [level]})["programming"], expected)

    def test_averages_top_three_without_padding(self):
        scores = skillprint.category_scores({"programming": [2, 2], "data": [5, 4, 3, 0]})
        self.assertEqual(scores["programming"], 40)
        self.assertEqual(scores["data"], 80)
        self.assertEqual(scores["systems"], 0)


class SnapshotTests(PilotBase):
    def test_snapshot_and_delta(self):
        set = StudentSkill.objects.create(student=self.a, skill=self.python, proficiency_level=2)
        skillprint.save_snapshot(actor=self.a.account, label="first")
        set.proficiency_level = 4
        set.save()
        skillprint.save_snapshot(actor=self.a.account, label="second")
        self.assertEqual(ProgressSnapshot.objects.filter(student=self.a).count(), 2)
        self.assertEqual(ProgressSnapshot.objects.filter(student=self.b).count(), 0)

    def test_save_progress_blocks_offsite_redirect(self):
        resp = self.login().post(reverse("pilot:save-progress"), {"next": "https://evil.example/"})
        self.assertEqual(resp.status_code, 302)
        self.assertNotIn("evil.example", resp["Location"])


class SeedTests(TestCase):
    def test_seed_is_idempotent_and_renders_escaped(self):
        call_command("seed_compass", verbosity=0)
        first = FieldNoteProfile.objects.count()
        call_command("seed_compass", verbosity=0)
        self.assertEqual(FieldNoteProfile.objects.count(), first)
        self.assertGreater(first, 0)
        note = FieldNoteProfile.objects.first()
        note.quote = "<script>alert(1)</script>"
        note.save()
        resp = self.client.get(reverse("reference:notes"))
        self.assertNotIn("<script>alert(1)</script>", resp.content.decode())


class ApiTests(PilotBase):
    def setUp(self):
        cache.clear()
        self.c = Client(enforce_csrf_checks=True)

    def csrf(self):
        token = self.c.get("/api/csrf").json()["data"]["csrfToken"]
        return {"HTTP_X_CSRFTOKEN": token}

    def post(self, path, body, **extra):
        return self.c.post(path, json.dumps(body), content_type="application/json", **extra)

    def test_login_requires_csrf(self):
        resp = self.post("/api/login", {"email": "pilot.a@example.test", "password": PASSWORD})
        self.assertEqual(resp.status_code, 403)

    def test_login_me_and_unexpected_fields(self):
        h = self.csrf()
        ok = self.post("/api/login", {"email": "pilot.a@example.test", "password": PASSWORD}, **h)
        self.assertEqual(ok.status_code, 200)
        self.assertTrue(self.c.get("/api/me").json()["ok"])
        bad = self.c.patch("/api/me", json.dumps({"display_name": "X", "is_staff": True}),
                           content_type="application/json", **self.csrf())
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(bad.json()["error"]["code"], "unexpected_fields")

    def test_anonymous_cannot_read_private_data(self):
        for path in ("/api/me", "/api/me/skills", "/api/dashboard-data"):
            self.assertIn(self.c.get(path).status_code, (401, 403))

    def test_bad_login_is_throttled(self):
        h = self.csrf()
        codes = [self.post("/api/login", {"email": "pilot.a@example.test", "password": "wrong"}, **h).status_code
                 for _ in range(15)]
        self.assertIn(429, codes)
