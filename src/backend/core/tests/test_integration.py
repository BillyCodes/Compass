"""Real template/form requests against the approved PostgreSQL-backed services."""
from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse
from accounts.models import Account, AccountRole
from auditing.models import AuditEvent
from comparisons.models import MatchResult
from comparisons.tests.factories import setup_actors, target, learning, draft, approve
from reference.models import ContentVersion
from reference.services import retire_content_version
from skills.models import StudentSkill, StudentCourse
from skills.services import set_student_skill


class FrontendIntegrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        setup_actors(cls)
        cls.student.account.set_password("Synthetic-Integration!2026")
        cls.student.account.save(update_fields=["password"])
        cls.career = target(cls)
        cls.course = learning(cls, cls.python, coverage=4)
        cls.resource = learning(cls, cls.sql, coverage=3, kind="resource")
        cls.insight = approve(cls, draft(cls, "insight"))

    def setUp(self):
        cache.clear()
        self.client.force_login(self.student.account)

    def skill(self, skill=None, level=3, **extra):
        data = {"skill-skill": (skill or self.python).pk, "skill-level": level, "skill-evidence": "Synthetic project"}
        data.update(extra)
        return self.client.post(reverse("skills:skillprint"), data)

    def compare(self):
        response = self.client.post(reverse("comparisons:run", args=[self.career.pk]), {"score":100,"student_id":self.other.pk})
        self.assertEqual(response.status_code, 302)
        return MatchResult.objects.get(student=self.student)

    def test_full_student_journey_uses_real_services_and_saved_recommendations(self):
        self.client.logout()
        response = self.client.post(reverse("accounts:login"), {"username":self.student.account.login_email.upper(),"password":"Synthetic-Integration!2026"})
        self.assertRedirects(response, reverse("core:dashboard"))
        self.assertRedirects(self.skill(), reverse("skills:skillprint"))
        before = list(StudentSkill.objects.filter(student=self.student).values_list("skill_id","proficiency_level"))
        response = self.client.post(reverse("skills:add-course"), {"course-course":self.course.pk})
        self.assertRedirects(response, reverse("skills:skillprint"))
        self.assertEqual(list(StudentSkill.objects.filter(student=self.student).values_list("skill_id","proficiency_level")),before)
        self.assertTrue(StudentCourse.objects.filter(student=self.student,course_item=self.course.item).exists())
        result = self.compare()
        self.assertEqual(str(result.score),"50.00")
        self.assertEqual(result.alg_version,"weighted_skill_match_v1")
        self.assertTrue(result.is_provisional)
        self.assertEqual(result.mandatory_status,"not_met")
        self.assertIsNone(result.inputs.get(skill=self.sql).level_used)
        self.assertEqual(result.recommendations.get().resource_version_id,self.course.pk)
        detail = self.client.get(reverse("comparisons:detail",args=[result.pk]))
        for text in ("50.00%", "Provisional", "Unreported proficiency", "Python", "Your learning route"):
            self.assertContains(detail,text)
        self.assertContains(self.client.get(reverse("comparisons:journey")),"50.00%")
        self.assertEqual(self.client.get(reverse("reference:learning",args=[self.course.pk])).status_code,200)
        self.assertEqual(self.client.get(reverse("reference:note",args=[self.insight.pk])).status_code,200)
        self.client.post(reverse("accounts:logout"))
        self.assertEqual(self.client.get(reverse("core:dashboard")).status_code,302)

    def test_all_unreported_inputs_are_not_saved(self):
        response = self.client.post(reverse("comparisons:run",args=[self.career.pk]),follow=True)
        self.assertContains(response,"Report at least one relevant proficiency")
        self.assertFalse(MatchResult.objects.filter(student=self.student).exists())

    def test_explicit_zero_is_reported_and_rendered_in_explorer(self):
        self.skill(level=0)
        self.assertEqual(StudentSkill.objects.get(student=self.student).proficiency_level,0)
        response = self.client.get(reverse("skills:explorer"))
        self.assertContains(response,"0 · None")
        result = self.compare()
        self.assertEqual(result.inputs.get(skill=self.python).level_used,0)
        self.assertEqual(result.outcomes.get(skill=self.python).status,"gap")

    def test_history_preserves_inputs_after_edits_and_retirement(self):
        self.skill()
        result = self.compare()
        self.skill(level=5)
        self.skill(self.sql,3)
        retire_content_version(actor=self.author,version_id=self.career.pk)
        retire_content_version(actor=self.author,version_id=self.course.pk)
        response = self.client.get(reverse("comparisons:detail",args=[result.pk]))
        self.assertContains(response,"50.00%")
        self.assertContains(response,"Your Skillprint has changed")
        self.assertContains(response,"No longer available")
        self.assertNotContains(response,reverse("reference:learning",args=[self.course.pk]))
        self.assertEqual(self.client.get(reverse("reference:learning",args=[self.course.pk])).status_code,404)
        self.assertEqual(self.client.post(reverse("comparisons:run",args=[self.career.pk])).status_code,404)

    def test_other_student_cannot_read_or_delete_saved_result(self):
        self.skill()
        result = self.compare()
        self.client.force_login(self.other.account)
        self.assertEqual(self.client.get(reverse("comparisons:detail",args=[result.pk])).status_code,404)
        self.assertEqual(self.client.post(reverse("comparisons:delete",args=[result.pk])).status_code,404)
        self.assertNotContains(self.client.get(reverse("comparisons:journey")),reverse("comparisons:detail",args=[result.pk]))
        self.assertTrue(MatchResult.objects.filter(pk=result.pk).exists())

    def test_mutations_cannot_target_another_students_skills_or_courses(self):
        set_student_skill(actor=self.other.account,skill_id=self.python.pk,proficiency_level=5)
        self.assertEqual(self.client.post(reverse("skills:update-skill",args=[self.python.pk]),{"level":1}).status_code,404)
        self.assertEqual(self.client.post(reverse("skills:remove-skill",args=[self.python.pk])).status_code,404)
        self.assertEqual(StudentSkill.objects.get(student=self.other).proficiency_level,5)
        self.assertEqual(self.client.post(reverse("skills:remove-course",args=[self.course.item_id])).status_code,404)

    def test_role_removal_blocks_every_student_area(self):
        AccountRole.objects.filter(account=self.student.account,role__role_name="student").delete()
        for name in ("core:dashboard","core:onboarding","skills:skillprint","skills:explorer","comparisons:compare","comparisons:journey","reference:notes","accounts:edit-profile"):
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name)).status_code,403)
        self.assertEqual(self.client.get(reverse("accounts:profile")).status_code,200)

    def test_private_pages_require_login_and_are_not_cached(self):
        for name in ("core:dashboard","skills:skillprint","skills:explorer","comparisons:compare","comparisons:journey","reference:notes","accounts:profile"):
            self.assertIn("no-store",self.client.get(reverse(name)).headers["Cache-Control"])
        self.client.logout()
        for name in ("core:dashboard","skills:skillprint","comparisons:compare","comparisons:journey","reference:notes"):
            response=self.client.get(reverse(name))
            self.assertEqual(response.status_code,302)
            self.assertTrue(response.url.startswith(reverse("accounts:login")))

    def test_only_published_reference_content_is_exposed(self):
        hidden=draft(self,"insight")
        hidden.title="Unreviewed private draft"
        hidden.save(update_fields=["title"])
        self.assertNotContains(self.client.get(reverse("reference:notes")),hidden.title)
        self.assertNotContains(self.client.get(reverse("core:home")),hidden.title)
        self.assertEqual(self.client.get(reverse("reference:note",args=[hidden.pk])).status_code,404)
        hidden_career=draft(self)
        self.assertEqual(self.client.post(reverse("comparisons:run",args=[hidden_career.pk])).status_code,404)

    def test_all_connected_pages_render_with_empty_or_populated_data(self):
        for name in ("core:home","core:onboarding","core:dashboard","skills:skillprint","skills:explorer","comparisons:compare","comparisons:journey","reference:notes","accounts:profile","accounts:edit-profile"):
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name)).status_code,200)
        self.assertContains(self.client.get(reverse("reference:learning",args=[self.resource.pk])),"https://example.test/learning")

    def test_unsafe_methods_cannot_mutate_and_csrf_is_enforced(self):
        self.skill()
        for name,args in (("skills:update-skill",[self.python.pk]),("skills:remove-skill",[self.python.pk]),("skills:add-course",[]),("comparisons:run",[self.career.pk])):
            self.assertEqual(self.client.get(reverse(name,args=args)).status_code,405)
        client=Client(enforce_csrf_checks=True)
        client.force_login(self.student.account)
        url=reverse("skills:skillprint")
        self.assertEqual(client.post(url,{"skill-skill":self.python.pk,"skill-level":4}).status_code,403)
        client.get(url)
        response=client.post(url,{"skill-skill":self.python.pk,"skill-level":4,"csrfmiddlewaretoken":client.cookies["csrftoken"].value})
        self.assertEqual(response.status_code,302)

    def test_profile_edit_is_allowlisted_and_owner_scoped(self):
        response=self.client.post(reverse("accounts:edit-profile"),{"display_name":"New student name","major":"CS","career_interests":"Data","graduation_year":2028,"account":self.other.account_id,"is_staff":True})
        self.assertRedirects(response,reverse("accounts:profile"))
        self.student.refresh_from_db()
        self.other.refresh_from_db()
        self.assertEqual(self.student.display_name,"New student name")
        self.assertNotEqual(self.other.display_name,"New student name")
        self.student.account.refresh_from_db()
        self.assertFalse(self.student.account.is_staff)

    def test_registration_creates_only_student_role_and_audits_assignment(self):
        self.client.logout()
        response=self.client.post(reverse("accounts:register"),{"name":"New User","email":"NEW.USER@EXAMPLE.TEST","major":"CS","password":"Synthetic-NewUser!2026","password_confirm":"Synthetic-NewUser!2026","role":"administrator","is_staff":True})
        self.assertRedirects(response,reverse("core:onboarding"))
        account=Account.objects.get(login_email="new.user@example.test")
        self.assertTrue(account.check_password("Synthetic-NewUser!2026"))
        self.assertFalse(account.is_staff)
        self.assertFalse(account.is_superuser)
        self.assertEqual(list(account.role_assignments.values_list("role__role_name",flat=True)),["student"])
        self.assertTrue(AuditEvent.objects.filter(subject_account=account,event_type="role.assigned").exists())

    def test_registration_validation_and_duplicate_email_do_not_create_accounts(self):
        self.client.logout()
        before=Account.objects.count()
        for email,password,confirm in ((self.student.account.login_email,"Synthetic-New!2026","Synthetic-New!2026"),("bad@example.test","short","different")):
            response=self.client.post(reverse("accounts:register"),{"name":"Invalid","email":email,"password":password,"password_confirm":confirm})
            self.assertEqual(response.status_code,200)
        self.assertEqual(Account.objects.count(),before)

    def test_invalid_skill_proficiency_does_not_write(self):
        response=self.skill(level=6)
        self.assertEqual(response.status_code,200)
        self.assertFalse(StudentSkill.objects.filter(student=self.student).exists())

    def test_result_deletion_removes_private_children_only(self):
        self.skill()
        result=self.compare()
        response=self.client.post(reverse("comparisons:delete",args=[result.pk]))
        self.assertRedirects(response,reverse("comparisons:journey"))
        self.assertFalse(MatchResult.objects.filter(pk=result.pk).exists())
        self.assertTrue(ContentVersion.objects.filter(pk=self.career.pk).exists())

    def test_stored_text_is_escaped_in_rendered_pages(self):
        self.student.display_name='<img src=x onerror="alert(1)">'
        self.student.save(update_fields=["display_name"])
        response=self.client.get(reverse("core:dashboard"))
        self.assertContains(response,"&lt;img")
        self.assertNotContains(response,'<img src=x onerror="alert(1)">')

    def test_registration_preserves_password_whitespace(self):
        self.client.logout()
        password = " Synthetic-Spaced!2026 "
        response = self.client.post(reverse("accounts:register"), {"name":"Spaced password", "email":"spaced@example.test", "password":password, "password_confirm":password})
        self.assertRedirects(response, reverse("core:onboarding"))
        self.assertTrue(Account.objects.get(login_email="spaced@example.test").check_password(password))
        self.client.logout()
        response = self.client.post(reverse("accounts:login"), {"username":"spaced@example.test", "password":password})
        self.assertRedirects(response, reverse("core:dashboard"))
