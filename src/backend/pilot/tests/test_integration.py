"""Regression coverage for the combined maintainer and student workflows."""
import io
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.urls import reverse

from comparisons.tests.test_services import ComparisonFixture
from comparisons.tests.factories import approve, draft, learning, setup_actors
from pilot.models import FieldNoteProfile, PostingMatch
from pilot.services import postings, resume
from reference.services import retire_content_version
from skills.models import StudentSkill


class PilotIntegrationTests(ComparisonFixture):
    def setUp(self):
        self.client.force_login(self.student.account)

    def test_private_result_preserves_recommendations_after_catalog_changes(self):
        course = learning(self, self.python)
        self.set_level(level=1)
        posting = postings.create_posting(actor=self.student.account, title="Synthetic developer",
                                         company="Synthetic company", description="Requirements:\nPython")
        match = postings.run_posting_match(actor=self.student.account, posting_id=posting.pk)
        self.assertEqual(match.recommendations[0]["version_id"], str(course.pk))
        retire_content_version(actor=self.author, version_id=course.pk)
        newer = learning(self, self.python)
        self.set_level(level=5)
        with patch("comparisons.services._recommendations", side_effect=AssertionError("History must not recompute")):
            response = self.client.get(reverse("comparisons:detail", args=[match.pk]))
        self.assertContains(response, "No longer available")
        self.assertNotContains(response, reverse("reference:learning", args=[newer.pk]))
        self.assertEqual(response.context["summary"]["score"], match.score)
        self.assertTrue(response.context["changed_since"])
        match.refresh_from_db()
        self.assertEqual(match.recommendations[0]["version_id"], str(course.pk))

    def test_private_result_cannot_be_modified_but_can_be_deleted(self):
        self.set_level()
        posting = postings.create_posting(actor=self.student.account, title="Developer", company="Sample", description="Python")
        match = postings.run_posting_match(actor=self.student.account, posting_id=posting.pk)
        for values in ({"score": 10}, {"detail": []}, {"recommendations": []}, {"student": self.other}):
            # Make the recommendations mutation distinct even when no courses exist.
            if "recommendations" in values:
                values = {"recommendations": [{"invalid": True}]}
            with self.subTest(values=values), self.assertRaises(IntegrityError), transaction.atomic():
                PostingMatch.objects.filter(pk=match.pk).update(**values)
        response = self.client.post(reverse("comparisons:delete", args=[match.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(PostingMatch.objects.filter(pk=match.pk).exists())

    def test_resume_review_preserves_explicit_zero(self):
        self.set_level(level=0)
        upload = SimpleUploadedFile("synthetic.txt", b"Python experience from synthetic university coursework and sample projects.")
        imp = resume.create_import(actor=self.student.account, uploaded=upload)
        url = reverse("pilot:resume-review", args=[imp.pk])
        self.assertContains(self.client.get(url), '<option value="0" selected>0', html=False)
        response = self.client.post(url, {f"keep_{self.python.pk}": "on", f"level_{self.python.pk}": "0"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(StudentSkill.objects.get(student=self.student, skill=self.python).proficiency_level, 0)

    def test_published_field_note_metadata_and_tags_are_frozen_and_escaped(self):
        version = draft(self, "insight")
        profile = FieldNoteProfile.objects.create(version=version, author_name="Synthetic author",
            author_role="Example role", author_org="Example", quote="<script>example</script>",
            working_on="Synthetic work", learn_next="Synthetic learning")
        profile.skills.add(self.python)
        approve(self, version)
        response = self.client.get(reverse("reference:notes"))
        self.assertContains(response, "&lt;script&gt;example&lt;/script&gt;")
        self.assertNotContains(response, "<script>example</script>")
        for mutation in (lambda: FieldNoteProfile.objects.filter(pk=profile.pk).update(quote="Changed"),
                         lambda: profile.skills.add(self.sql), lambda: profile.skills.clear(),
                         lambda: profile.delete()):
            with self.assertRaises(IntegrityError), transaction.atomic():
                mutation()

    def test_direct_publication_is_visible_in_new_student_ui(self):
        self.client.force_login(self.author)
        version = draft(self, "insight")
        response = self.client.post(reverse("maintenance:publish_content", args=[version.pk]),
                                    {"expected_revision": version.draft_revision})
        self.assertEqual(response.status_code, 302)
        version.refresh_from_db()
        self.assertEqual(version.status, "published")
        self.assertFalse(version.reviews.exists())
        self.client.force_login(self.student.account)
        self.assertContains(self.client.get(reverse("reference:note", args=[version.pk])), version.title)
        self.assertEqual(self.client.get(reverse("maintenance:dashboard")).status_code, 403)

    def test_api_lists_have_pages_and_keep_owned_history_private(self):
        from comparisons.services import create_comparison
        self.set_level()
        create_comparison(actor=self.student.account, target_version_id=self.version.pk)
        self.set_level(student=self.other)
        create_comparison(actor=self.other.account, target_version_id=self.version.pk)
        with patch("core.pagination.PAGE_SIZE", 1):
            response = self.client.get("/api/skills", {"page": 2})
            self.assertEqual(response.json()["pagination"]["page"], 2)
            self.assertEqual(len(response.json()["data"]), 1)
            history = self.client.get("/api/comparisons").json()
        self.assertEqual(history["pagination"]["total"], 1)
        self.assertEqual(len(history["data"]), 1)
        self.assertIn("no-store", response.headers["Cache-Control"])

    def test_docx_text_is_read_without_saving_an_upload(self):
        from docx import Document
        document = Document()
        document.add_paragraph("Python and SQL experience through synthetic coursework and projects.")
        data = io.BytesIO()
        document.save(data)
        upload = SimpleUploadedFile("synthetic.docx", data.getvalue())
        imp = resume.create_import(actor=self.student.account, uploaded=upload)
        self.assertIn(str(self.python.pk), [row["skill_id"] for row in imp.detected])

    def test_pdf_text_is_read_and_encrypted_pdf_is_rejected(self):
        # A tiny synthetic PDF with one text stream and a built-in font.
        stream = b"BT /F1 12 Tf 20 50 Td (Python and SQL synthetic university coursework and projects.) Tj ET"
        objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 100] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"]
        data, offsets = b"%PDF-1.4\n", [0]
        for index, obj in enumerate(objects, 1):
            offsets.append(len(data))
            data += str(index).encode() + b" 0 obj\n" + obj + b"\nendobj\n"
        start = len(data)
        data += b"xref\n0 6\n0000000000 65535 f \n"
        data += b"".join(f"{offset:010} 00000 n \n".encode() for offset in offsets[1:])
        data += b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n" + str(start).encode() + b"\n%%EOF\n"
        imp = resume.create_import(actor=self.student.account, uploaded=SimpleUploadedFile("synthetic.pdf", data))
        self.assertIn(str(self.python.pk), [row["skill_id"] for row in imp.detected])
        from pypdf import PdfReader, PdfWriter
        writer = PdfWriter()
        writer.append(PdfReader(io.BytesIO(data)))
        writer.encrypt("synthetic-password")
        encrypted = io.BytesIO()
        writer.write(encrypted)
        with self.assertRaisesMessage(resume.ResumeError, "password-protected"):
            resume.create_import(actor=self.student.account, uploaded=SimpleUploadedFile("synthetic.pdf", encrypted.getvalue()))


class PilotMigrationTests(TransactionTestCase):
    def test_existing_private_result_survives_upgrade_without_invented_recommendations(self):
        setup_actors(self)
        executor = MigrationExecutor(connection)
        try:
            executor.migrate([("pilot", "0001_initial")])
            old_apps = executor.loader.project_state([("pilot", "0001_initial")]).apps
            old_match = old_apps.get_model("pilot", "PostingMatch")
            legacy = old_match.objects.create(student_id=self.student.pk, target_title="Legacy synthetic result",
                target_company="Example", alg_version="weighted_skill_match_v1", score=100,
                mandatory_status="met", reported_count=1, relevant_count=1,
                is_provisional=False, detail=[])
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
        saved = PostingMatch.objects.get(pk=legacy.pk)
        self.assertEqual(saved.target_title, "Legacy synthetic result")
        self.assertEqual(saved.recommendations, [])
        with self.assertRaises(IntegrityError), transaction.atomic():
            PostingMatch.objects.filter(pk=saved.pk).update(score=0)
