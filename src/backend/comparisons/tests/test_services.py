from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.utils import timezone

from reference.models import ContentItem, ContentVersion
from reference.services import retire_content_version, set_content_details
from skills.models import Skill, StudentSkill
from skills.services import set_student_skill
from comparisons.models import MatchInputSkill, MatchResult, MatchSkillResult, Recommendation
from comparisons.services import create_comparison, delete_match, get_match, list_matches
from .factories import approve, draft, learning, setup_actors, target


class ComparisonFixture(TestCase):
    @classmethod
    def setUpTestData(cls):
        setup_actors(cls)
        cls.version = target(cls)

    def set_level(self,skill=None,level=3,student=None):
        return set_student_skill(actor=(student or self.student).account,skill_id=(skill or self.python).pk,proficiency_level=level)

    def compare(self,actor=None,version=None):
        return create_comparison(actor=actor or self.student.account,target_version_id=(version or self.version).pk)



class ComparisonServiceTests(ComparisonFixture):
    def test_private_partial_comparison_has_exact_unknown_snapshots(self):
        self.set_level()
        result = self.compare()
        self.assertEqual(result.score,Decimal("50.00"))
        self.assertEqual(result.mandatory_status,"not_met")
        self.assertTrue(result.finalized)
        self.assertTrue(result.is_provisional)
        self.assertEqual((result.reported_count,result.relevant_count),(1,2))
        self.assertEqual(dict(result.inputs.values_list("skill_id","level_used")),{self.python.pk:3,self.sql.pk:None})
        self.assertEqual(result.outcomes.get(skill=self.python).gap,1)
        self.assertEqual(result.outcomes.get(skill=self.sql).status,"unreported")
        self.assertEqual(result.alg_version,"weighted_skill_match_v1")

    def test_complete_inputs_and_zero_remain_distinct_from_unknown(self):
        self.set_level(level=5)
        self.set_level(self.sql,0)
        result = self.compare()
        self.assertEqual(result.score,Decimal("66.67"))
        self.assertEqual(result.mandatory_status,"met")
        self.assertFalse(result.is_provisional)
        self.assertEqual(result.inputs.get(skill=self.sql).level_used,0)

    def test_owner_scopes_list_read_delete_and_children(self):
        self.set_level()
        result = self.compare()
        self.assertEqual(list_matches(actor=self.student.account).count(),1)
        self.assertFalse(list_matches(actor=self.other.account).exists())
        for service in (get_match,delete_match):
            with self.assertRaises(MatchResult.DoesNotExist):
                service(actor=self.other.account,match_id=result.pk)
        self.assertEqual(get_match(actor=self.student.account,match_id=result.pk).inputs.count(),2)
        delete_match(actor=self.student.account,match_id=result.pk)
        self.assertFalse(MatchResult.objects.exists())
        self.assertFalse(MatchInputSkill.objects.exists())
        self.assertFalse(MatchSkillResult.objects.exists())
        self.assertTrue(ContentVersion.objects.filter(pk=self.version.pk).exists())

    def test_anonymous_maintainer_disabled_and_profileless_accounts_denied(self):
        from accounts.models import Account, AccountRole, Role
        profileless = Account.objects.create_user("profileless@example.test")
        AccountRole.objects.create(account=profileless,role=Role.objects.get(role_name="student"))
        self.student.account.is_active = False
        for actor in (AnonymousUser(),self.author,self.student.account,profileless):
            with self.subTest(actor=actor):
                with self.assertRaises(PermissionDenied):
                    create_comparison(actor=actor,target_version_id=self.version.pk)
                with self.assertRaises(PermissionDenied):
                    list_matches(actor=actor)

    def test_owner_and_score_cannot_be_supplied(self):
        for extra in ({"student_id":self.other.pk},{"score":100}):
            with self.assertRaises(TypeError):
                create_comparison(actor=self.student.account,target_version_id=self.version.pk,**extra)

    def test_all_missing_inputs_do_not_save_any_result(self):
        with self.assertRaises(ValidationError):
            self.compare()
        self.assertFalse(MatchResult.objects.exists())
        self.assertFalse(MatchInputSkill.objects.exists())

    def test_draft_learning_and_retired_targets_rejected(self):
        self.set_level()
        for version in (draft(self),learning(self,self.python)):
            with self.assertRaises(ValidationError):
                self.compare(version=version)
        retire_content_version(actor=self.author,version_id=self.version.pk)
        with self.assertRaises(ValidationError):
            self.compare()

    def test_retired_item_and_skill_rejected(self):
        self.set_level()
        ContentItem.objects.filter(pk=self.version.item_id).update(retired_at=timezone.now())
        with self.assertRaises(ValidationError):
            self.compare()
        ContentItem.objects.filter(pk=self.version.item_id).update(retired_at=None)
        Skill.objects.filter(pk=self.sql.pk).update(status="retired")
        with self.assertRaises(ValidationError):
            self.compare()

    def test_expired_job_rejected(self):
        self.set_level()
        job = draft(self,"job")
        set_content_details(actor=self.author,version_id=job.pk,expected_revision=job.draft_revision,
                            expires_at=timezone.now()+timezone.timedelta(days=1))
        job = approve(self,job)
        with patch("comparisons.services.timezone.now",return_value=timezone.now()+timezone.timedelta(days=2)):
            with self.assertRaises(ValidationError):
                self.compare(version=job)

    def test_history_does_not_change_after_profile_edit_or_retirement(self):
        self.set_level()
        result = self.compare()
        self.set_level(level=5)
        self.set_level(self.sql,3)
        retire_content_version(actor=self.author,version_id=self.version.pk)
        saved = get_match(actor=self.student.account,match_id=result.pk)
        self.assertEqual(saved.score,Decimal("50.00"))
        self.assertEqual(saved.inputs.get(skill=self.python).level_used,3)
        self.assertIsNone(saved.inputs.get(skill=self.sql).level_used)
        with self.assertRaises(ProtectedError):
            self.version.delete()

    def test_failure_rolls_back_parent_and_all_children(self):
        self.set_level()
        with patch("comparisons.services._recommendations",side_effect=RuntimeError("synthetic failure")):
            with self.assertRaises(RuntimeError):
                self.compare()
        self.assertFalse(MatchResult.objects.exists())
        self.assertFalse(MatchInputSkill.objects.exists())
        self.assertFalse(MatchSkillResult.objects.exists())

    def test_student_deletion_removes_only_their_private_results(self):
        self.set_level()
        self.set_level(student=self.other)
        own = self.compare()
        other = self.compare(actor=self.other.account)
        self.student.delete()
        self.assertFalse(MatchResult.objects.filter(pk=own.pk).exists())
        self.assertTrue(MatchResult.objects.filter(pk=other.pk).exists())
        self.assertTrue(ContentVersion.objects.filter(pk=self.version.pk).exists())

    def test_result_and_children_cannot_be_edited_or_appended(self):
        self.set_level()
        result = self.compare()
        mutations = [
            lambda: MatchResult.objects.filter(pk=result.pk).update(score=100),
            lambda: result.inputs.update(level_used=5),
            lambda: result.outcomes.update(gap=0,status="met"),
            lambda: MatchInputSkill.objects.create(match=result,skill=Skill.objects.get(skill_name="Publication fixture skill"),level_used=5),
        ]
        for mutation in mutations:
            with self.assertRaises(IntegrityError),transaction.atomic():
                mutation()

    def test_individual_snapshot_deletion_cannot_commit(self):
        self.set_level()
        result = self.compare()
        for rows in (result.inputs,result.outcomes):
            with self.assertRaises(IntegrityError),transaction.atomic():
                rows.first().delete()
                with connection.cursor() as cursor:
                    cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")

    def test_database_has_all_five_composite_foreign_keys(self):
        tables = {"match_result":["match_target_kind_fk"],"recommendation":["recommendation_version_kind_fk"],
                  "match_skill_result":["outcome_match_target_fk","outcome_requirement_fk","outcome_input_fk"]}
        with connection.cursor() as cursor:
            for table,names in tables.items():
                constraints = connection.introspection.get_constraints(cursor,table)
                for name in names:
                    self.assertTrue(constraints[name]["foreign_key"])

    def test_database_rejects_nonfinalized_parent_at_transaction_end(self):
        with self.assertRaises(IntegrityError),transaction.atomic():
            MatchResult.objects.create(student=self.student,target_version=self.version,target_kind="career",alg_version="weighted_skill_match_v1",
                                       score=100,mandatory_status="met",reported_count=2,relevant_count=2,is_provisional=False)
            with connection.cursor() as cursor:
                cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")

    def test_zero_level_only_publication_is_rejected(self):
        from reference.models import ContentRequirement
        version = draft(self)
        ContentRequirement.objects.filter(version=version).update(required_level=0)
        with self.assertRaises(ValidationError):
            approve(self,version)


class RecommendationTests(ComparisonFixture):
    def test_mandatory_gap_precedes_larger_optional_gap(self):
        mandatory = learning(self,self.python,coverage=4)
        optional = learning(self,self.sql,coverage=3,kind="resource")
        self.set_level(level=3)
        self.set_level(self.sql,0)
        result = self.compare()
        suggestions = list(result.recommendations.all())
        self.assertEqual([r.resource_version_id for r in suggestions],[mandatory.pk,optional.pk])
        self.assertEqual(suggestions[0].reason["skills"][0]["skill_id"],str(self.python.pk))
        self.assertEqual(result.recommendation_count,2)

    def test_unknown_skills_and_no_improvement_do_not_generate_recommendations(self):
        learning(self,self.sql,coverage=3)
        learning(self,self.python,coverage=2)
        self.set_level(level=3)
        self.assertFalse(self.compare().recommendations.exists())

    def test_latest_available_edition_per_item_and_retirement_history(self):
        old = learning(self,self.python,coverage=4)
        latest = learning(self,self.python,coverage=5,item=old.item)
        self.set_level(level=1)
        result = self.compare()
        self.assertEqual(list(result.recommendations.values_list("resource_version_id",flat=True)),[latest.pk])
        retire_content_version(actor=self.author,version_id=latest.pk)
        self.assertEqual(result.recommendations.get().resource_version_id,latest.pk)
        self.assertEqual(self.compare().recommendations.get().resource_version_id,old.pk)

    def test_retired_item_and_draft_only_resources_excluded(self):
        retired = learning(self,self.python)
        ContentItem.objects.filter(pk=retired.item_id).update(retired_at=timezone.now())
        draft(self,"resource")
        self.set_level()
        self.assertFalse(self.compare().recommendations.exists())

    def test_recommendations_do_not_alter_proficiency(self):
        learning(self,self.python)
        self.set_level()
        before = list(StudentSkill.objects.values_list("student_id","skill_id","proficiency_level"))
        self.compare()
        self.assertEqual(list(StudentSkill.objects.values_list("student_id","skill_id","proficiency_level")),before)

    def test_recommendations_are_immutable_and_delete_with_result(self):
        learning(self,self.python)
        self.set_level()
        result = self.compare()
        recommendation = result.recommendations.get()
        with self.assertRaises(IntegrityError),transaction.atomic():
            Recommendation.objects.filter(pk=recommendation.pk).update(reason={})
        with self.assertRaises(IntegrityError),transaction.atomic():
            recommendation.delete()
            with connection.cursor() as cursor:
                cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
        delete_match(actor=self.student.account,match_id=result.pk)
        self.assertFalse(Recommendation.objects.exists())
