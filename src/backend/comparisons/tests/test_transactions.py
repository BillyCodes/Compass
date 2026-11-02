"""Real commits, independent connections, and reversible PostgreSQL guards."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event

from django.db import connection, IntegrityError, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

from accounts.models import Account
from comparisons.models import MatchInputSkill, MatchResult, MatchSkillResult
from comparisons.services import create_comparison
from skills.services import set_student_skill
from .factories import setup_actors, target


class ComparisonTransactionTests(TransactionTestCase):
    def setUp(self):
        setup_actors(self)
        self.version = target(self)
        set_student_skill(actor=self.student.account,skill_id=self.python.pk,proficiency_level=3)

    def staged(self,**extra):
        fields = dict(student=self.student,target_version=self.version,target_kind="career",alg_version="weighted_skill_match_v1",
                      score=50,mandatory_status="not_met",reported_count=1,relevant_count=2,is_provisional=True)
        fields.update(extra)
        return MatchResult.objects.create(**fields)

    def add_snapshots(self,result):
        MatchInputSkill.objects.bulk_create([
            MatchInputSkill(match=result,skill=self.python,level_used=3),
            MatchInputSkill(match=result,skill=self.sql,level_used=None),
        ])
        MatchSkillResult.objects.bulk_create([
            MatchSkillResult(match=result,target_version=self.version,skill=self.python,status="gap",gap=1),
            MatchSkillResult(match=result,target_version=self.version,skill=self.sql,status="unreported",gap=None),
        ])

    def test_successful_service_commits_and_persists(self):
        result = create_comparison(actor=self.student.account,target_version_id=self.version.pk)
        self.assertTrue(MatchResult.objects.get(pk=result.pk).finalized)
        self.assertEqual(result.inputs.count(),2)

    def test_incomplete_transaction_is_rejected_on_real_commit(self):
        with self.assertRaises(IntegrityError),transaction.atomic():
            self.staged()
        self.assertFalse(MatchResult.objects.exists())

    def test_forged_score_and_completeness_cannot_commit(self):
        for extra in ({"score":99},{"reported_count":2,"is_provisional":False},{"mandatory_status":"met"}):
            with self.subTest(extra=extra), self.assertRaises(IntegrityError),transaction.atomic():
                result = self.staged(**extra)
                self.add_snapshots(result)
                result.finalized = True
                result.save(update_fields=["finalized"])
        self.assertFalse(MatchResult.objects.exists())

    def test_outcome_cannot_reference_another_target_or_unrelated_skill(self):
        from skills.models import Skill
        another = target(self,"job")
        unrelated = Skill.objects.create(skill_name="Unrelated historical input")
        for version,skill in ((another,self.python),(self.version,unrelated)):
            with self.subTest(version=version.pk,skill=skill.pk),self.assertRaises(IntegrityError),transaction.atomic():
                result = self.staged()
                MatchInputSkill.objects.create(match=result,skill=skill,level_used=3)
                MatchSkillResult.objects.create(match=result,target_version=version,skill=skill,status="met",gap=0)

    def test_typed_target_cannot_point_at_a_learning_version(self):
        from .factories import learning
        course = learning(self,self.python)
        with self.assertRaises(IntegrityError),transaction.atomic():
            self.staged(target_version=course,target_kind="career")

    def test_individual_deletion_rejected_but_full_private_deletion_commits(self):
        from comparisons.services import delete_match
        result = create_comparison(actor=self.student.account,target_version_id=self.version.pk)
        with self.assertRaises(IntegrityError),transaction.atomic():
            result.outcomes.first().delete()
        delete_match(actor=self.student.account,match_id=result.pk)
        self.assertFalse(MatchResult.objects.exists())

    def test_comparison_waits_for_in_progress_proficiency_write(self):
        written = Event()
        comparing = Event()
        release = Event()
        def write():
            try:
                with transaction.atomic():
                    actor = Account.objects.get(pk=self.student.account_id)
                    set_student_skill(actor=actor,skill_id=self.python.pk,proficiency_level=4)
                    written.set()
                    if not release.wait(timeout=5):
                        raise TimeoutError("The proficiency transaction was not released.")
            finally:
                connection.close()
        def compare():
            try:
                comparing.set()
                actor = Account.objects.get(pk=self.student.account_id)
                return create_comparison(actor=actor,target_version_id=self.version.pk).score
            finally:
                connection.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            writer = pool.submit(write)
            try:
                self.assertTrue(written.wait(timeout=5))
                reader = pool.submit(compare)
                self.assertTrue(comparing.wait(timeout=5))
            finally:
                release.set()
            writer.result(timeout=10)
            self.assertEqual(str(reader.result(timeout=10)),"66.67")

    def test_integrity_and_publication_migrations_reverse_and_reinstall(self):
        executor = MigrationExecutor(connection)
        try:
            executor.migrate([("comparisons","0001_initial"),("reference","0006_publication_guards")])
            with connection.cursor() as cursor:
                cursor.execute("SELECT to_regprocedure('comparison_assert_complete(uuid)')")
                self.assertIsNone(cursor.fetchone()[0])
                cursor.execute("SELECT to_regprocedure('reference_assert_publishable_base_v1(uuid,uuid)')")
                self.assertIsNone(cursor.fetchone()[0])
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
        with connection.cursor() as cursor:
            cursor.execute("SELECT to_regprocedure('comparison_assert_complete(uuid)')")
            self.assertIsNotNone(cursor.fetchone()[0])
