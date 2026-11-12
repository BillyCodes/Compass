"""Provenance, original reflections and upgrades preserve publication integrity."""
import json

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection, IntegrityError, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from comparisons.tests.factories import setup_actors
from reference.models import ContentItem, ContentSource, ContentVersion, ReferenceSource
from reference.services import (attach_source, create_content_item, create_draft_version,
    create_reference_source, create_successor_draft, edit_draft_source, publish_content_version,
    update_draft_version)


class ProvenanceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        setup_actors(cls)

    def draft(self, origin="external", **fields):
        item = create_content_item(actor=self.author, kind="insight")
        return create_draft_version(actor=self.author, item_id=item.pk, title="Keep learning",
                                    body="A personal reflection on practicing consistently.", origin=origin, **fields)

    def publish(self, version):
        version.refresh_from_db()
        return publish_content_version(actor=self.author, version_id=version.pk,
                                       expected_revision=version.draft_revision)

    def cite(self, version, usage="excerpt", provider="other", **fields):
        metadata = dict(provider=provider, publisher="Example publisher", author="Example author",
            source_url="https://example.test/article", license_name="CC BY 4.0",
            license_url="https://creativecommons.org/licenses/by/4.0/", attribution_text="Credit: Example author",
            source_version="2026 edition", external_id="example-1", file_sha256="a" * 64,
            raw_metadata={"source_record": "example-1", "original_label": "Original wording"})
        metadata.update(fields)
        source = create_reference_source(actor=self.author, source_title="Example material",
            source_url_or_identifier="example-1", **metadata)
        version.refresh_from_db()
        return attach_source(actor=self.author, version_id=version.pk, source_id=source.pk,
            expected_revision=version.draft_revision, usage=usage,
            changes="Compass summarized this material." if usage in ("adapted", "interpretation") else "")

    def test_original_reflection_publishes_without_fabricated_source_and_is_labeled(self):
        version = self.publish(self.draft("original", original_author="Project student", originality_confirmed=True))
        self.assertFalse(version.source_links.exists())
        self.client.force_login(self.student.account)
        response = self.client.get(reverse("reference:note", args=[version.pk]))
        self.assertContains(response, "Original personal reflection by Project student")
        self.assertNotContains(response, "years</span>")

    def test_original_authorship_is_required_and_only_insights_qualify(self):
        for fields in ({}, {"original_author": "Student"}, {"originality_confirmed": True}):
            with self.subTest(fields=fields), self.assertRaises(ValidationError):
                self.publish(self.draft("original", **fields))
        item = create_content_item(actor=self.author, kind="career")
        with self.assertRaises(ValidationError):
            create_draft_version(actor=self.author, item_id=item.pk, title="Career", body="Body", origin="original")

    def test_external_and_synthetic_content_still_need_sources(self):
        for origin in ("external", "synthetic"):
            with self.subTest(origin=origin), self.assertRaisesMessage(ValidationError, "At least one reference source"):
                self.publish(self.draft(origin))

    def test_external_metadata_and_usage_are_enforced_in_database(self):
        version = self.draft()
        source = create_reference_source(actor=self.author, source_title="Incomplete", source_url_or_identifier="test:incomplete")
        attach_source(actor=self.author, version_id=version.pk, source_id=source.pk,
                      expected_revision=version.draft_revision)
        with self.assertRaisesMessage(ValidationError, "Complete source provenance"):
            self.publish(version)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ContentVersion.objects.filter(pk=version.pk).update(status="published", published_by=self.author,
                                                               published_at=timezone.now())

    def test_original_with_borrowed_material_cannot_skip_source_provenance(self):
        version = self.draft("original", original_author="Student", originality_confirmed=True)
        self.cite(version, license_name="")
        with self.assertRaisesMessage(ValidationError, "Complete source provenance"):
            self.publish(version)

    def test_link_only_does_not_invent_a_license_for_uncopied_content(self):
        version = self.draft()
        self.cite(version, usage="link", license_name="", license_url="", attribution_text="")
        self.assertEqual(self.publish(version).status, "published")

    def test_onet_file_identity_and_adaptation_notes_are_required(self):
        for fields in ({"source_version": ""}, {"external_id": ""}, {"file_sha256": ""}):
            version = self.draft()
            self.cite(version, provider="onet", **fields)
            with self.subTest(fields=fields), self.assertRaises(ValidationError):
                self.publish(version)
        version = self.draft()
        link = self.cite(version, provider="onet", usage="adapted")
        ContentSource.objects.filter(pk=link.pk).update(changes="")
        with self.assertRaises(ValidationError):
            self.publish(version)

    def test_complete_sources_publish_and_visible_credits_escape_html(self):
        version = self.draft()
        self.cite(version, provider="onet", usage="adapted", attribution_text="Credit <script>example</script>")
        version = self.publish(version)
        self.client.force_login(self.student.account)
        response = self.client.get(reverse("reference:note", args=[version.pk]))
        self.assertContains(response, "Sources and attribution")
        self.assertContains(response, "&lt;script&gt;example&lt;/script&gt;")
        self.assertContains(response, "https://creativecommons.org/licenses/by/4.0/")
        self.assertContains(response, "Compass summarized this material.")

    def test_metadata_usage_and_origin_are_immutable_after_publication(self):
        version = self.draft()
        link = self.cite(version)
        self.publish(version)
        for model, pk, fields in (
            (ContentVersion, version.pk, {"origin": "synthetic"}),
            (ContentVersion, version.pk, {"originality_confirmed": True}),
            (ReferenceSource, link.source_id, {"license_name": "Another license"}),
            (ContentSource, link.pk, {"changes": "Rewrite history"}),
        ):
            with self.subTest(model=model), self.assertRaises(IntegrityError), transaction.atomic():
                model.objects.filter(pk=pk).update(**fields)

    def test_origin_revision_and_same_operation_publication_bypass(self):
        version = self.draft()
        before = version.draft_revision
        ContentVersion.objects.filter(pk=version.pk).update(origin="original", original_author="Student",
                                                          originality_confirmed=True)
        version.refresh_from_db()
        self.assertEqual(version.draft_revision, before + 1)
        with self.assertRaisesMessage(ValidationError, "changed"):
            update_draft_version(actor=self.author, version_id=version.pk, expected_revision=before,
                                 title=version.title, body=version.body)
        other = self.draft()
        with self.assertRaises(IntegrityError), transaction.atomic():
            ContentVersion.objects.filter(pk=other.pk).update(origin="original", original_author="Student",
                originality_confirmed=True, status="published", published_by=self.author, published_at=timezone.now())

    def test_successor_copies_provenance_and_corrections_preserve_published_sources(self):
        version = self.draft()
        link = self.cite(version, usage="interpretation")
        self.publish(version)
        successor = create_successor_draft(actor=self.author, version_id=version.pk)
        copied = successor.source_links.get()
        self.assertEqual(copied.usage, link.usage)
        self.assertEqual(copied.changes, link.changes)
        self.assertEqual(successor.origin, "external")
        corrected = edit_draft_source(actor=self.author, version_id=successor.pk,
            source_id=link.source_id, expected_revision=successor.draft_revision,
            source_title="Corrected citation", source_url_or_identifier="example:corrected", author="Corrected author")
        self.assertNotEqual(corrected.pk, link.source_id)
        self.assertEqual(corrected.file_sha256, "a" * 64)
        self.assertEqual(corrected.raw_metadata["source_record"], "example-1")
        self.assertEqual(ReferenceSource.objects.get(pk=link.source_id).author, "Example author")

    def test_non_editor_cannot_create_original_content(self):
        item = create_content_item(actor=self.author, kind="insight")
        with self.assertRaises(PermissionDenied):
            create_draft_version(actor=self.student.account, item_id=item.pk, title="Note", body="Body", origin="original")

    def test_source_forms_save_and_correct_metadata_and_usage(self):
        version = self.draft()
        self.client.force_login(self.author)
        data = dict(source_title="MIT material", source_url_or_identifier="mit:resource", provider="mit",
            publisher="MIT OpenCourseWare", author="Named instructor", source_url="https://ocw.mit.edu/",
            license_name="CC BY-NC-SA 4.0", license_url="https://creativecommons.org/licenses/by-nc-sa/4.0/",
            attribution_text="Credit: named instructor, MIT OCW", source_version="Fall 2020",
            external_id="course-1", file_sha256="", raw_metadata=json.dumps({"edition": "Fall 2020"}),
            usage="adapted", changes="Compass summary", attribution_note="Original terms apply",
            expected_revision=version.draft_revision)
        response = self.client.post(reverse("maintenance:add_source", args=[version.pk]), data)
        self.assertEqual(response.status_code, 302)
        link = version.source_links.select_related("source").get()
        self.assertEqual(link.source.provider, "mit")
        self.assertEqual(link.source.raw_metadata, {"edition": "Fall 2020"})
        self.assertEqual((link.usage, link.changes), ("adapted", "Compass summary"))
        version.refresh_from_db()
        data.update(expected_revision=version.draft_revision, attribution_note="Updated attribution note")
        response = self.client.post(reverse("maintenance:edit_source", args=[version.pk, link.source_id]), data)
        self.assertEqual(response.status_code, 302)
        link.refresh_from_db()
        self.assertEqual(link.attribution_note, "Updated attribution note")
        self.assertEqual(self.publish(version).status, "published")

    def test_maintainer_can_create_and_publish_original_note_through_existing_forms(self):
        self.client.force_login(self.author)
        response = self.client.post(reverse("maintenance:create_content"), dict(kind="insight", title="Original note",
            body="Keep practicing.", origin="original", original_author="Student author", originality_confirmed="on"))
        self.assertEqual(response.status_code, 302)
        version = ContentVersion.objects.get(title="Original note")
        response = self.client.post(reverse("maintenance:publish_content", args=[version.pk]),
                                    {"expected_revision": version.draft_revision})
        self.assertEqual(response.status_code, 302)
        version.refresh_from_db()
        self.assertEqual(version.status, "published")


class ProvenanceMigrationTests(TransactionTestCase):
    def test_upgrade_preserves_unclassified_published_history_and_unknown_rights(self):
        setup_actors(self)
        executor = MigrationExecutor(connection)
        try:
            executor.migrate([("reference", "0008_direct_publication")])
            apps = executor.loader.project_state([("reference", "0008_direct_publication")]).apps
            item = apps.get_model("reference", "ContentItem").objects.create(kind="insight")
            old_version = apps.get_model("reference", "ContentVersion")
            version = old_version.objects.create(item_id=item.pk, kind="insight", version_no=1,
                title="Historical note", body="Historical body", created_by_id=self.author.pk)
            source = apps.get_model("reference", "ReferenceSource").objects.create(
                source_title="Historical source", source_url_or_identifier="fixture:historical")
            apps.get_model("reference", "ContentSource").objects.create(version_id=version.pk, source_id=source.pk)
            old_version.objects.filter(pk=version.pk).update(status="published", published_by_id=self.author.pk,
                                                            published_at=timezone.now())
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
        saved = ContentVersion.objects.get(pk=version.pk)
        self.assertEqual((saved.origin, saved.body, saved.status), ("legacy", "Historical body", "published"))
        saved_source = ReferenceSource.objects.get(pk=source.pk)
        self.assertEqual((saved_source.provider, saved_source.license_name), ("unknown", ""))
        self.assertEqual(saved.source_links.get().usage, "unknown")
        successor = create_successor_draft(actor=self.author, version_id=saved.pk)
        with self.assertRaisesMessage(ValidationError, "Classify"):
            publish_content_version(actor=self.author, version_id=successor.pk, expected_revision=successor.draft_revision)
