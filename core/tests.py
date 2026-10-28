"""
Test Launch 01 acceptance tests.

Mirrors the Engineering Blueprint:
  §2.5  Acceptance summary
  §12.2 Primary trial-run script
  §12.3 Negative test matrix
  §9    Known-input comparison examples (manually computed below)

Run:  python manage.py test core
"""
import io
import json
from decimal import Decimal

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import Client, TestCase

from core.models import Account, CareerProfile, JobPosting, MatchResult, ResumeImport, Student, StudentSkill
from core.services import comparison, postings, resume, skillprint
from core.services.comparison import Requirement

PW_A, PW_B = "CompassDemo-A1", "CompassDemo-B2"
A, B, DIS = "student.a@compass.test", "student.b@compass.test", "disabled@compass.test"


class SeededTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_compass", verbosity=0, stdout=io.StringIO())

    def setUp(self):
        cache.clear()

    def login(self, email=A, pw=PW_A, client=None):
        c = client or self.client
        return c.post("/login/", {"email": email, "password": pw})

    def api(self, method, url, body=None, client=None):
        c = client or self.client
        if method == "get":
            return c.get(url)
        return getattr(c, method)(url, data=json.dumps(body or {}), content_type="application/json")


# ---------------------------------------------------------------------------
# §9  Comparison engine — known-input examples, computed by hand
# ---------------------------------------------------------------------------
class ComparisonEngineTests(TestCase):
    R = staticmethod(lambda sid, lvl, w=1, m=False: Requirement(sid, sid.title(), "programming", lvl, w, m))

    def test_known_input_weighted_score(self):
        # python: has 3, needs 3 → 1.0 × w2 = 2.0
        # sql:    has 2, needs 3 → 0.6 × w1 = 0.6
        # aws:    missing        → 0.0 × w1 = 0.0
        # score = 100 × 2.6 / 4 = 65.0
        reqs = [self.R("python", 3, 2, True), self.R("sql", 3, 1), self.R("aws", 3, 1)]
        out = comparison.compare({"python": 3, "sql": 2}, reqs)
        self.assertEqual(out["score"], Decimal("65.0"))
        self.assertEqual(out["requirements_met"], 1)
        self.assertEqual((out["mandatory_met"], out["mandatory_total"]), (1, 1))
        self.assertEqual(out["status"], "Developing Match")
        outcomes = {d["skill_id"]: d["outcome"] for d in out["detail"]}
        self.assertEqual(outcomes, {"python": "met", "sql": "below", "aws": "missing"})

    def test_gap_lookup_table(self):
        self.assertEqual(comparison.satisfaction(5, 3), 1.0)
        self.assertEqual(comparison.satisfaction(2, 3), 0.6)
        self.assertEqual(comparison.satisfaction(1, 3), 0.3)
        self.assertEqual(comparison.satisfaction(1, 5), 0.1)
        self.assertEqual(comparison.satisfaction(None, 3), 0.0)

    def test_mandatory_gap_blocks_strong_match(self):
        # 9 of 10 weight met, but the one missing skill is mandatory → 90.0, not Strong
        reqs = [self.R(f"s{i}", 2) for i in range(9)] + [self.R("crit", 2, 1, True)]
        out = comparison.compare({f"s{i}": 3 for i in range(9)}, reqs)
        self.assertEqual(out["score"], Decimal("90.0"))
        self.assertEqual(out["status"], "Developing Match")

    def test_strong_match(self):
        out = comparison.compare({"a": 4, "b": 3}, [self.R("a", 3, 1, True), self.R("b", 3)])
        self.assertEqual(out["score"], Decimal("100.0"))
        self.assertEqual(out["status"], "Strong Match")

    def test_edge_cases(self):
        self.assertEqual(comparison.compare({"a": 3}, [])["status"], "Not comparable")       # no requirements
        self.assertEqual(comparison.compare({}, [self.R("a", 3)])["score"], Decimal("0.0"))   # no skills
        dup = comparison.compare({"a": 3}, [self.R("a", 2), self.R("a", 4, 2, True)])         # duplicates collapse to strictest
        self.assertEqual(dup["requirements_total"], 1)
        self.assertEqual(dup["detail"][0]["required_level"], 4)
        self.assertTrue(dup["detail"][0]["mandatory"])
        bad = comparison.compare({"a": 3}, [self.R("a", 0), self.R("b", 9)])                  # invalid levels ignored
        self.assertEqual(bad["status"], "Not comparable")

    def test_deterministic(self):
        reqs = [self.R("python", 3, 2, True), self.R("sql", 3), self.R("aws", 4)]
        self.assertEqual(comparison.compare({"python": 2}, reqs), comparison.compare({"python": 2}, reqs))


# ---------------------------------------------------------------------------
# §12.2 Primary trial-run script, end to end
# ---------------------------------------------------------------------------
class TrialRunScript(SeededTestCase):
    def test_full_student_journey(self):
        c = Client()
        # 2. Create account; no credential material in the response
        r = c.post("/register/", {"name": "Riley Test", "email": "riley@compass.test", "major": "CS",
                                   "password": "Sturdy-Pass-2026", "password_confirm": "Sturdy-Pass-2026"})
        self.assertRedirects(r, "/welcome/")
        acct = Account.objects.get(email="riley@compass.test")
        self.assertTrue(acct.password.startswith("pbkdf2_"))
        self.assertTrue(Student.objects.filter(account=acct).exists())
        self.assertNotContains(c.get("/dashboard/"), "Sturdy-Pass-2026")
        c.post("/logout/")

        # 3. Invalid login → generic failure, no session
        r = c.post("/login/", {"email": "riley@compass.test", "password": "wrong-password"})
        self.assertContains(r, "don&#x27;t match an active account")
        self.assertNotIn("_auth_user_id", c.session)

        # 4–5. Login, own dashboard
        self.login("riley@compass.test", "Sturdy-Pass-2026", client=c)
        self.assertContains(c.get("/dashboard/"), "Riley")

        # 6. Protected write persists and reloads
        c.post("/skillprint/", {"skill-skill": "python", "skill-level": "3", "skill-evidence": "Class project"})
        self.assertContains(c.get("/skillprint/"), "Class project")
        self.assertEqual(StudentSkill.objects.get(student__account=acct, skill_id="python").level, 3)

        # 8. Career comparison → saved, server-computed result
        career = CareerProfile.objects.get(slug="cloud-engineer")
        r = c.post(f"/compare/career/{career.pk}/")
        result = MatchResult.objects.filter(student__account=acct).latest("created_at")
        self.assertRedirects(r, f"/results/{result.pk}/")
        self.assertEqual(result.algorithm_version, comparison.ALGORITHM_VERSION)

        # 9–10. Logout, then replaying a private request is denied
        c.post("/logout/")
        r = c.get("/dashboard/")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login/", r["Location"])
        self.assertEqual(self.api("get", "/api/me", client=c).status_code, 401)

    def test_old_session_cookie_is_dead_after_logout(self):
        c = Client()
        self.login(client=c)
        stolen = c.cookies["sessionid"].value
        c.post("/logout/")
        replay = Client()
        replay.cookies["sessionid"] = stolen
        self.assertEqual(replay.get("/api/me").status_code, 401)


# ---------------------------------------------------------------------------
# §12.3 Negative test matrix and §8.2 threats
# ---------------------------------------------------------------------------
class NegativeTests(SeededTestCase):
    def test_duplicate_email_rejected(self):
        r = self.api("post", "/api/register", {"name": "X", "email": A, "password": "Another-Pass-77"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("email", r.json()["error"]["fields"])

    def test_role_escalation_on_register_rejected(self):
        r = self.api("post", "/api/register", {"name": "Eve", "email": "eve@compass.test", "password": "Another-Pass-77", "role": "admin"})
        self.assertEqual(r.status_code, 400)
        self.assertFalse(Account.objects.filter(email="eve@compass.test").exists())
        # The HTML form ignores extra fields entirely
        self.client.post("/register/", {"name": "Eve", "email": "eve2@compass.test", "password": "Another-Pass-77",
                                        "password_confirm": "Another-Pass-77", "role": "admin", "is_staff": "on"})
        eve = Account.objects.get(email="eve2@compass.test")
        self.assertEqual((eve.role, eve.is_staff, eve.is_superuser), ("student", False, False))

    def test_student_a_cannot_read_or_change_student_b(self):
        b = Student.objects.get(account__email=B)
        b_result = comparison.run_and_save(b, career=CareerProfile.objects.get(slug="security-analyst"))
        b_level = StudentSkill.objects.get(student=b, skill_id="java").level
        self.login()
        # B's saved result → 404, contents never rendered
        r = self.client.get(f"/results/{b_result.pk}/")
        self.assertEqual(r.status_code, 404)
        self.assertNotContains(r, "Taylor", status_code=404)
        # A's skill routes act only on A's own records, whatever is sent
        self.client.post("/skillprint/skill/java/level/", {"level": "1", "student": str(b.pk)})
        self.assertEqual(StudentSkill.objects.get(student=b, skill_id="java").level, b_level)
        r = self.api("put", "/api/me/skills/java", {"level": 1, "student_id": str(b.pk)})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(StudentSkill.objects.get(student=b, skill_id="java").level, b_level)
        # B's resume import
        imp = ResumeImport.objects.create(student=b, filename="b.pdf", char_count=100, detected=[])
        self.assertEqual(self.client.get(f"/resume/{imp.pk}/review/").status_code, 404)
        # API never returns B's data
        self.assertEqual(self.api("get", "/api/me").json()["data"]["email"], A)

    def test_private_posting_of_b_not_usable_by_a(self):
        b = Student.objects.get(account__email=B)
        posting, _ = postings.create_student_posting(b, "Secret Role", "B Corp", "Requirements\n- Python\n- SQL\n" + "x" * 80)
        self.login()
        self.assertEqual(self.client.post(f"/compare/posting/{posting.pk}/").status_code, 404)
        self.assertEqual(self.api("post", "/api/comparisons", {"posting_id": posting.pk}).status_code, 404)
        self.assertNotContains(self.client.get("/compare/"), "Secret Role")

    def test_invalid_skill_id(self):
        self.login()
        self.assertEqual(self.api("put", "/api/me/skills/not-a-skill", {"level": 3}).status_code, 404)
        self.assertEqual(self.client.post("/skillprint/skill/not-a-skill/level/", {"level": 3}).status_code, 404)

    def test_oversized_and_malformed_input(self):
        self.login()
        self.assertEqual(self.api("put", "/api/me/skills/python", {"level": 9}).status_code, 400)
        self.assertEqual(self.api("put", "/api/me/skills/python", {"level": "3"}).status_code, 400)
        self.assertEqual(self.api("patch", "/api/me", {"name": "x" * 500}).status_code, 400)
        r = self.client.post("/api/me/skills/python", data="{not json", content_type="application/json")
        self.assertEqual(r.status_code, 400)
        r = self.client.post("/api/me/skills/python", data=json.dumps({"level": 3, "evidence": "x" * 40000}), content_type="application/json")
        self.assertEqual(r.status_code, 413)

    def test_disabled_account_denied(self):
        r = self.login(DIS, "CompassDemo-X9")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "don&#x27;t match an active account")
        self.assertEqual(self.api("post", "/api/login", {"email": DIS, "password": "CompassDemo-X9"}).status_code, 401)

    def test_disabling_account_ends_live_session(self):
        self.login()
        self.assertEqual(self.client.get("/dashboard/").status_code, 200)
        Account.objects.filter(email=A).update(status="disabled")
        self.assertEqual(self.client.get("/dashboard/").status_code, 302)
        self.assertEqual(self.api("get", "/api/me").status_code, 401)

    def test_logged_out_protected_endpoints(self):
        for url in ["/dashboard/", "/skillprint/", "/compare/", "/journey/", "/field-notes/", "/resume/"]:
            self.assertEqual(self.client.get(url).status_code, 302, url)
        for url in ["/api/me", "/api/me/skills", "/api/dashboard-data", "/api/comparisons"]:
            self.assertEqual(self.client.get(url).status_code, 401, url)

    def test_script_text_is_inert(self):
        self.login()
        payload = '<script>alert("x")</script>'
        self.client.post("/skillprint/", {"skill-skill": "python", "skill-level": "3", "skill-evidence": payload})
        r = self.client.get("/skillprint/")
        self.assertNotContains(r, payload)
        self.assertContains(r, "&lt;script&gt;")

    def test_client_cannot_submit_score(self):
        self.login()
        career = CareerProfile.objects.get(slug="cloud-engineer")
        r = self.api("post", "/api/comparisons", {"career_id": career.pk, "match_score": 100})
        self.assertEqual(r.status_code, 400)
        r = self.api("post", "/api/comparisons", {"career_id": career.pk})
        self.assertEqual(r.status_code, 201)
        expected = comparison.compare(comparison.student_levels(Student.objects.get(account__email=A)), comparison.requirements_for_career(career))
        self.assertEqual(Decimal(str(r.json()["data"]["score"])), expected["score"])

    def test_login_throttle(self):
        for _ in range(5):
            self.login(A, "bad-password-x")
        r = self.login(A, PW_A)
        self.assertContains(r, "Too many attempts")

    def test_csrf_enforced(self):
        c = Client(enforce_csrf_checks=True)
        r = c.post("/api/login", data=json.dumps({"email": A, "password": PW_A}), content_type="application/json")
        self.assertEqual(r.status_code, 403)

    def test_password_hash_never_in_api(self):
        self.login()
        body = json.dumps([self.api("get", u).json() for u in ["/api/me", "/api/dashboard-data", "/api/me/skills"]])
        self.assertNotIn("pbkdf2", body)
        self.assertNotIn("password", body)


# ---------------------------------------------------------------------------
# Resume upload, posting parser, Skillprint, progress
# ---------------------------------------------------------------------------
RESUME = """Jordan Rivera — Computer Science, Jackson State University
Skills: Python, SQL, PostgreSQL, Linux, Git, Docker, AWS
Projects
- Built a REST API in Python with Flask and PostgreSQL for a course scheduling app.
- Deployed services on AWS EC2 and automated setup with Bash scripts on Linux.
Experience
- Teaching Assistant, Data Structures & Algorithms. Led review sessions; strong communication.
"""


class ResumeAndPostingTests(SeededTestCase):
    def test_detects_skills_with_word_boundaries(self):
        found = {s["skill_id"]: s for s in resume.detect_skills(RESUME + "\nJavaScript")}
        for sid in ["python", "sql", "linux", "git", "docker", "aws", "rest-apis", "data-structures", "communication"]:
            self.assertIn(sid, found)
        self.assertNotIn("java", found)          # "JavaScript" must not count as Java
        self.assertLessEqual(max(s["suggested_level"] for s in found.values()), 3)

    def test_upload_review_and_apply(self):
        self.login(B, PW_B)
        f = SimpleUploadedFile("resume.txt", RESUME.encode(), content_type="text/plain")
        r = self.client.post("/resume/", {"resume": f})
        imp = ResumeImport.objects.get(student__account__email=B)
        self.assertRedirects(r, f"/resume/{imp.pk}/review/")
        before = StudentSkill.objects.filter(student__account__email=B).count()
        r = self.client.post(f"/resume/{imp.pk}/review/", {"keep_python": "on", "level_python": "4", "keep_docker": "on", "level_docker": "2"})
        self.assertRedirects(r, "/dashboard/")
        b_skills = dict(StudentSkill.objects.filter(student__account__email=B).values_list("skill_id", "level"))
        self.assertEqual((b_skills["python"], b_skills["docker"]), (4, 2))
        self.assertNotIn("aws", b_skills)       # unchecked skills are not saved
        self.assertEqual(len(b_skills), before + 2)
        self.assertTrue(Student.objects.get(account__email=B).snapshots.exists())

    def test_rejects_bad_files(self):
        self.login()
        for name, data in [("resume.exe", b"MZ..."), ("resume.pdf", b"not a pdf at all, just text" * 3), ("r.txt", b"short")]:
            r = self.client.post("/resume/", {"resume": SimpleUploadedFile(name, data)})
            self.assertEqual(r.status_code, 200, name)
            self.assertContains(r, 'class="alert error"')
        big = SimpleUploadedFile("big.txt", b"a" * (2 * 1024 * 1024 + 10))
        self.assertContains(self.client.post("/resume/", {"resume": big}), "larger than 2 MB")

    def test_real_pdf_and_docx(self):
        from docx import Document
        from pypdf import PdfWriter
        buf = io.BytesIO(); d = Document(); [d.add_paragraph(line) for line in RESUME.splitlines()]; d.save(buf)
        self.assertIn("Python", resume.extract_text(SimpleUploadedFile("r.docx", buf.getvalue())))
        w = PdfWriter(); w.add_blank_page(612, 792); pbuf = io.BytesIO(); w.write(pbuf)
        with self.assertRaises(resume.ResumeError):        # blank/scanned PDF → clear message
            resume.extract_text(SimpleUploadedFile("r.pdf", pbuf.getvalue()))

    def test_posting_parser_sections(self):
        text = "About us\nWe use Kubernetes.\n\nRequirements\n- Python\n- Linux administration\n\nPreferred\n- Terraform\n"
        rows = {r["skill"].skill_id: r for r in postings.parse_requirements(text)}
        self.assertTrue(rows["python"]["mandatory"])
        self.assertTrue(rows["linux"]["mandatory"])
        self.assertFalse(rows["iac"]["mandatory"])
        self.assertFalse(rows["kubernetes"]["mandatory"])

    def test_pasted_posting_compare(self):
        self.login()
        r = self.client.post("/compare/", {"title": "Cloud Intern", "company": "Acme",
                                          "description": "Requirements\n- Python and Linux\n- AWS\nPreferred\n- Docker, Terraform\n" + "Join us. " * 10})
        result = MatchResult.objects.filter(student__account__email=A, target_type="posting").latest("created_at")
        self.assertRedirects(r, f"/results/{result.pk}/")
        self.assertEqual(result.mandatory_total, 3)

    def test_skillprint_category_scores(self):
        # top-3 average: data skills 4 and 3 → (4+3+0)/3/5×100 = 46.7
        scores = skillprint.category_scores({"data": [4, 3]})
        self.assertEqual(scores["data"], 46.7)
        self.assertEqual(scores["security"], 0.0)

    def test_save_progress_and_journey(self):
        self.login()
        n = Student.objects.get(account__email=A).snapshots.count()
        self.client.post("/skillprint/save/", {"label": "Before career fair"})
        self.assertEqual(Student.objects.get(account__email=A).snapshots.count(), n + 1)
        self.assertContains(self.client.get("/journey/"), "Before career fair")

    def test_result_survives_skill_changes(self):
        self.login()
        result = MatchResult.objects.filter(student__account__email=A).latest("created_at")
        score = result.score
        StudentSkill.objects.filter(student__account__email=A).update(level=1)
        r = self.client.get(f"/results/{result.pk}/")
        self.assertContains(r, "Your Skillprint changed after this comparison")
        result.refresh_from_db()
        self.assertEqual(result.score, score)

    def test_field_notes_visible(self):
        self.login()
        r = self.client.get("/field-notes/")
        self.assertContains(r, "fictional")
        self.assertContains(self.client.get("/field-notes/?skill=linux"), "Linux and networking")

    def test_every_page_renders(self):
        self.login()
        for url in ["/dashboard/", "/welcome/", "/skillprint/", "/explore/", "/explore/?q=docker", "/resume/",
                    "/compare/", "/journey/", "/field-notes/", "/profile/"]:
            self.assertEqual(self.client.get(url).status_code, 200, url)
