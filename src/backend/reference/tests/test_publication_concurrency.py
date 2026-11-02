"""Separate real PostgreSQL connections exercise publication serialization."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event

from django.db import connection, IntegrityError, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

from accounts.models import Account, AccountRole, Role
from reference.models import ContentRequirement
from reference.services import create_content_item, create_draft_version, publish_content_version, review_content_version
from reference.tests.factories import prepare_for_publication


class PublicationConcurrencyTests(TransactionTestCase):
    def setUp(self):
        # TransactionTestCase flushes seed data; recreate only the fixed vocabulary.
        for name in ("student","maintainer","administrator"):
            Role.objects.get_or_create(role_name=name)
        self.author = Account.objects.create_user("concurrent.author@example.test")
        self.reviewer = Account.objects.create_user("concurrent.reviewer@example.test")
        for actor in (self.author,self.reviewer):
            AccountRole.objects.create(account=actor,role=Role.objects.get(role_name="maintainer"))

    def test_concurrent_draft_creation_assigns_distinct_sequential_versions(self):
        item = create_content_item(actor=self.author,kind="career")
        def create():
            try:
                actor = Account.objects.get(pk=self.author.pk)
                return create_draft_version(actor=actor,item_id=item.pk,title="Concurrent draft",body="Body").version_no
            finally:
                connection.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(create),pool.submit(create)]
            self.assertEqual(sorted(f.result(timeout=10) for f in futures),[1,2])

    def test_publish_commit_prevents_concurrent_requirement_or_source_mutation(self):
        for target in ("requirement","source"):
            with self.subTest(target=target):
                item = create_content_item(actor=self.author,kind="career")
                version = create_draft_version(actor=self.author,item_id=item.pk,title="Publication race",body="Body")
                prepare_for_publication(version,self.author)
                review_content_version(actor=self.reviewer,version_id=version.pk,expected_revision=version.draft_revision,decision="approved")
                requirement = version.requirements.get()
                source = version.source_links.get().source
                published = Event()
                mutation_started = Event()
                release = Event()
                def publish():
                    try:
                        with transaction.atomic():
                            actor = Account.objects.get(pk=self.author.pk)
                            publish_content_version(actor=actor,version_id=version.pk,expected_revision=version.draft_revision)
                            published.set()
                            if not release.wait(timeout=5):
                                raise TimeoutError("The publication test did not release its transaction.")
                    finally:
                        connection.close()
                def mutate():
                    try:
                        mutation_started.set()
                        if target == "requirement":
                            ContentRequirement.objects.filter(pk=requirement.pk).update(required_level=5)
                        else:
                            type(source).objects.filter(pk=source.pk).update(source_title="Racing edit")
                        return "changed"
                    except IntegrityError:
                        return "rejected"
                    finally:
                        connection.close()
                with ThreadPoolExecutor(max_workers=2) as pool:
                    publisher = pool.submit(publish)
                    try:
                        self.assertTrue(published.wait(timeout=5))
                        mutator = pool.submit(mutate)
                        self.assertTrue(mutation_started.wait(timeout=5))
                    finally:
                        release.set()
                    publisher.result(timeout=10)
                    self.assertEqual(mutator.result(timeout=10),"rejected")
                version.refresh_from_db()
                self.assertEqual(version.status,"published")
                requirement.refresh_from_db()
                source.refresh_from_db()
                self.assertEqual(requirement.required_level,2)
                self.assertEqual(source.source_title,"Synthetic reference")

    def test_publication_guard_migration_can_be_reversed_and_reinstalled(self):
        executor = MigrationExecutor(connection)
        try:
            executor.migrate([("reference","0005_contentreview")])
            with connection.cursor() as cursor:
                cursor.execute("SELECT to_regprocedure('reference_version_guard()')")
                self.assertIsNone(cursor.fetchone()[0])
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
        with connection.cursor() as cursor:
            cursor.execute("SELECT to_regprocedure('reference_version_guard()')")
            self.assertIsNotNone(cursor.fetchone()[0])
