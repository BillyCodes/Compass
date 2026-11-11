"""Maintainers correct editions without rewriting published content or history."""
from unittest.mock import patch

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from auditing.models import AuditEvent
from comparisons.services import create_comparison, get_match
from comparisons.tests.factories import approve, draft, learning, setup_actors, target
from pilot.models import FieldNoteProfile
from reference.models import ContentItem, ContentVersion
from reference.selectors import latest_available
from reference.services import create_company, create_successor_draft, publish_content_version, set_content_details, update_draft_version
from skills.services import set_student_skill


class MaintenanceLifecycleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        setup_actors(cls)
        cls.career = target(cls)

    def setUp(self):
        self.client.force_login(self.author)

    def test_dashboard_offers_actions_and_get_does_not_mutate(self):
        response = self.client.get(reverse("maintenance:dashboard"))
        for action in ("successor", "retire"):
            url = reverse(f"maintenance:{action}", args=[self.career.pk])
            self.assertContains(response, url)
            count = ContentVersion.objects.count()
            confirm = self.client.get(url)
            self.assertEqual(confirm.status_code, 200)
            self.assertIn("no-store", confirm.headers["Cache-Control"])
            self.assertEqual(ContentVersion.objects.count(), count)
            self.career.refresh_from_db()
            self.assertEqual(self.career.status, "published")

    def test_successor_copies_requirements_sources_and_reuses_item(self):
        response = self.client.post(reverse("maintenance:successor", args=[self.career.pk]))
        successor = self.career.item.versions.get(status="draft")
        self.assertRedirects(response, reverse("maintenance:edit_content", args=[successor.pk]))
        self.assertEqual(successor.version_no, 2)
        self.assertEqual(successor.created_by_id, self.author.pk)
        self.assertEqual((successor.title, successor.body), (self.career.title, self.career.body))
        self.assertIsNone(successor.published_at)
        self.assertIsNone(successor.published_by_id)
        self.assertFalse(successor.reviews.exists())
        self.assertCountEqual(successor.source_links.values_list("source_id", flat=True),
                              self.career.source_links.values_list("source_id", flat=True))
        fields = ("skill_id", "required_level", "weight", "mandatory")
        self.assertCountEqual(successor.requirements.values_list(*fields), self.career.requirements.values_list(*fields))
        repeated = create_successor_draft(actor=self.author, version_id=self.career.pk)
        self.assertEqual(repeated.pk, successor.pk)
        self.assertEqual(self.career.item.versions.filter(status="draft").count(), 1)

    def test_details_mappings_and_field_note_metadata_are_copied(self):
        for kind in ("course", "resource", "job", "insight"):
            with self.subTest(kind=kind):
                source = learning(self, self.python, kind=kind) if kind in ("course", "resource") else draft(self, kind)
                if kind == "job":
                    company = create_company(actor=self.author, company_name="Synthetic employer")
                    set_content_details(actor=self.author, version_id=source.pk, expected_revision=source.draft_revision,
                        company_id=company.pk, location="Remote", expires_at=timezone.now() + timezone.timedelta(days=30))
                if kind == "insight":
                    profile = FieldNoteProfile.objects.create(version=source, author_name="Synthetic author",
                        author_role="Engineer", author_org="Sample", quote="Synthetic quote",
                        working_on="Synthetic work", learn_next="Synthetic learning")
                    profile.skills.add(self.python)
                if source.status == "draft":
                    source = approve(self, source)
                successor = create_successor_draft(actor=self.author, version_id=source.pk)
                fields = ("skill_id", "coverage_level")
                self.assertCountEqual(successor.skill_mappings.values_list(*fields), source.skill_mappings.values_list(*fields))
                original_details = getattr(source, "details", None)
                if original_details is not None:
                    for field in original_details._meta.concrete_fields:
                        if field.name != "version":
                            self.assertEqual(getattr(successor.details, field.attname), getattr(original_details, field.attname))
                if kind == "insight":
                    self.assertEqual(successor.field_note.quote, source.field_note.quote)
                    self.assertCountEqual(successor.field_note.skills.all(), source.field_note.skills.all())
                    successor.field_note.quote = "Corrected draft quote"
                    successor.field_note.save(update_fields=["quote"])
                    self.assertEqual(FieldNoteProfile.objects.get(pk=source.pk).quote, "Synthetic quote")

    def test_publishing_successor_preserves_old_edition_and_saved_result(self):
        set_student_skill(actor=self.student.account, skill_id=self.python.pk, proficiency_level=3)
        result = create_comparison(actor=self.student.account, target_version_id=self.career.pk)
        successor = create_successor_draft(actor=self.author, version_id=self.career.pk)
        successor = update_draft_version(actor=self.author, version_id=successor.pk,
            expected_revision=successor.draft_revision, title="Corrected career", body="Corrected description")
        publish_content_version(actor=self.author, version_id=successor.pk, expected_revision=successor.draft_revision)
        self.assertEqual(latest_available("career").get(item_id=self.career.item_id).pk, successor.pk)
        self.career.refresh_from_db()
        self.assertEqual(self.career.title, "Synthetic comparison target")
        saved = get_match(actor=self.student.account, match_id=result.pk)
        self.assertEqual(saved.target_version_id, self.career.pk)
        self.assertEqual(saved.score, result.score)

    def test_retirement_removes_edition_preserves_history_and_records_actor(self):
        set_student_skill(actor=self.student.account, skill_id=self.python.pk, proficiency_level=3)
        result = create_comparison(actor=self.student.account, target_version_id=self.career.pk)
        response = self.client.post(reverse("maintenance:retire", args=[self.career.pk]))
        self.assertRedirects(response, reverse("maintenance:dashboard"))
        self.career.refresh_from_db()
        self.assertEqual(self.career.status, "retired")
        self.assertFalse(latest_available("career").filter(pk=self.career.pk).exists())
        self.assertEqual(get_match(actor=self.student.account, match_id=result.pk).score, result.score)
        event = AuditEvent.objects.get(content_version=self.career, event_type="content.retired")
        self.assertEqual(event.actor_account_id, self.author.pk)
        self.client.post(reverse("maintenance:retire", args=[self.career.pk]))
        self.assertEqual(AuditEvent.objects.filter(content_version=self.career, event_type="content.retired").count(), 1)
        self.assertEqual(create_successor_draft(actor=self.author, version_id=self.career.pk).version_no, 2)

    def test_role_and_csrf_checks_cover_both_actions(self):
        for action in ("successor", "retire"):
            url = reverse(f"maintenance:{action}", args=[self.career.pk])
            csrf_client = Client(enforce_csrf_checks=True)
            csrf_client.force_login(self.author)
            self.assertEqual(csrf_client.post(url).status_code, 403)
            self.client.force_login(self.student.account)
            self.assertEqual(self.client.get(url).status_code, 403)
            self.assertEqual(self.client.post(url).status_code, 403)
            self.client.logout()
            self.assertEqual(self.client.get(url).status_code, 302)
            self.client.force_login(self.author)
            self.assertEqual(self.client.put(url).status_code, 405)
        with self.assertRaises(PermissionDenied):
            create_successor_draft(actor=self.student.account, version_id=self.career.pk)

    def test_business_administrator_can_use_both_actions(self):
        from accounts.models import AccountRole, Role
        AccountRole.objects.create(account=self.other.account, role=Role.objects.get(role_name="administrator"))
        self.client.force_login(self.other.account)
        response = self.client.post(reverse("maintenance:successor", args=[self.career.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.career.item.versions.get(status="draft").created_by_id, self.other.account_id)
        response = self.client.post(reverse("maintenance:retire", args=[self.career.pk]))
        self.assertRedirects(response, reverse("maintenance:dashboard"))

    def test_draft_and_retired_item_rejected_and_copy_failure_rolls_back(self):
        source = draft(self)
        with self.assertRaises(ValidationError):
            create_successor_draft(actor=self.author, version_id=source.pk)
        ContentItem.objects.filter(pk=self.career.item_id).update(retired_at=timezone.now())
        with self.assertRaises(ValidationError):
            create_successor_draft(actor=self.author, version_id=self.career.pk)
        ContentItem.objects.filter(pk=self.career.item_id).update(retired_at=None)
        before = self.career.item.versions.count()
        with patch("reference.services.ContentSource.objects.bulk_create", side_effect=RuntimeError("Copy failed")):
            with self.assertRaises(RuntimeError):
                create_successor_draft(actor=self.author, version_id=self.career.pk)
        self.assertEqual(self.career.item.versions.count(), before)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.career.title = "Forbidden overwrite"
            self.career.save(update_fields=["title"])
