"""Curated editing preserves authorization, provenance and immutable editions."""
import csv
import io
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.test import TestCase, TransactionTestCase, Client
from django.db import close_old_connections, connection
from accounts.models import Account
from django.urls import reverse

from comparisons.tests.factories import setup_actors
from reference.curation import publication_issues
from reference.models import ContentItem, ContentSource, ContentVersion, OnetCareerIdentity, ReferenceSource
from reference.onet_import import CAREERS, import_careers, import_plan, plan_fingerprint
from reference.services import (create_content_item, create_draft_version, publish_content_version,
                                set_field_note_profile, set_requirement, update_draft_version)
from skills.models import Skill


class CurationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        setup_actors(cls)

    def setUp(self):
        self.client.force_login(self.author)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.write_files()

    def write_files(self, suffix=''):
        with (self.directory / 'occupation_data.csv').open('w') as f:
            writer = csv.writer(f)
            writer.writerow(['O*NET-SOC Code', 'Title', 'Description'])
            for code, (title, _) in CAREERS.items():
                writer.writerow([code, title, 'Occupation description ' + suffix])
        with (self.directory / 'software_skills.csv').open('w') as f:
            writer = csv.writer(f)
            writer.writerow(['O*NET-SOC Code', 'Title', 'Workplace Example', 'Element ID', 'Element Name', 'Hot Technology', 'In Demand'])
            for code, (title, _) in CAREERS.items():
                writer.writerow([code, title, 'Python', '2.F.1', 'Programming software', 'Y', 'N'])
                writer.writerow([code, title, 'Structured query language SQL', '2.F.2', 'Database software', 'Y', 'Y'])

    def apply(self):
        return import_careers(actor=self.author, dry_run=False, directory=self.directory)

    def test_dry_run_and_command_default_leave_database_untouched(self):
        before = (ContentItem.objects.count(), ReferenceSource.objects.count(), Skill.objects.count())
        plan = import_careers(actor=self.author, directory=self.directory)
        self.assertEqual(len(plan), 5)
        out = io.StringIO()
        call_command('import_onet_careers', actor=self.author.login_email, source_dir=str(self.directory), stdout=out)
        self.assertIn('Dry run: no database changes', out.getvalue())
        self.assertEqual(before, (ContentItem.objects.count(), ReferenceSource.objects.count(), Skill.objects.count()))

    def test_import_is_repeatable_and_preserves_raw_sources_without_scoring_claims(self):
        self.apply()
        self.assertEqual(ContentVersion.objects.filter(status='draft', origin='external').count(), 5)
        self.assertEqual(OnetCareerIdentity.objects.count(), 5)
        self.assertEqual(ReferenceSource.objects.count(), 10)
        self.assertEqual(Skill.objects.filter(skill_name__iexact='Python').count(), 1)
        self.assertEqual(Skill.objects.get(skill_name='Python').category, '')  # Existing catalog untouched.
        version = ContentVersion.objects.first()
        self.assertFalse(version.requirements.exists())
        self.assertTrue(publication_issues(version))
        software = version.source_links.get(source__source_title__contains='software_skills').source
        self.assertEqual(software.raw_metadata['software_examples'][0]['Workplace Example'], 'Python')
        self.assertEqual(len(software.file_sha256), 64)
        # Preserve manual editorial work when importing the same files again.
        update_draft_version(actor=self.author, version_id=version.pk, expected_revision=version.draft_revision,
                             title='Edited career title', body='Edited career body')
        self.assertTrue(all(row['action'] == 'unchanged' for row in self.apply()))
        version.refresh_from_db()
        self.assertEqual(version.body, 'Edited career body')
        self.assertEqual(ContentVersion.objects.count(), 5)
        self.assertEqual(ReferenceSource.objects.count(), 10)

    def test_malformed_input_and_stale_preview_cannot_partially_import(self):
        fingerprint = plan_fingerprint(import_plan(self.directory))
        self.write_files('changed')
        with self.assertRaisesMessage(ValidationError, 'files changed'):
            import_careers(actor=self.author, dry_run=False, directory=self.directory, expected_fingerprint=fingerprint)
        self.assertFalse(ContentItem.objects.exists())
        (self.directory / 'software_skills.csv').write_text('wrong,columns\n1,2\n')
        with self.assertRaises(ValidationError):
            self.apply()
        self.assertFalse(ContentItem.objects.exists())

    def test_import_rolls_back_entire_batch_if_a_skill_is_retired(self):
        self.python.status = 'retired'
        self.python.save()
        with self.assertRaisesMessage(ValidationError, 'existing Python skill'):
            self.apply()
        self.assertFalse(OnetCareerIdentity.objects.exists())
        self.assertFalse(ContentItem.objects.exists())
        self.assertFalse(ReferenceSource.objects.exists())

    def test_changed_data_refuses_to_overwrite_a_draft(self):
        self.apply()
        self.write_files('new description')
        with self.assertRaisesMessage(ValidationError, 'existing draft'):
            self.apply()
        self.assertEqual(ContentVersion.objects.count(), 5)
        self.assertFalse(ContentVersion.objects.filter(body__contains='new description').exists())

    def test_changed_data_creates_successor_and_preserves_published_history(self):
        plan = self.apply()
        for row in plan:
            version = row['version']
            version.refresh_from_db()
            set_requirement(actor=self.author, version_id=version.pk, expected_revision=version.draft_revision,
                            skill_id=self.python.pk, required_level=2, mandatory=False, weight='1')
            version.refresh_from_db()
            publish_content_version(actor=self.author, version_id=version.pk, expected_revision=version.draft_revision)
        historical_sources = set(ReferenceSource.objects.values_list('pk', flat=True))
        self.write_files('new description')
        plan = self.apply()
        self.assertTrue(all(row['action'] == 'successor' for row in plan))
        self.assertEqual(ContentVersion.objects.filter(status='published', body='Occupation description').count(), 5)
        self.assertEqual(ContentVersion.objects.filter(status='draft', version_no=2).count(), 5)
        self.assertEqual(ContentSource.objects.filter(version__status='published', source_id__in=historical_sources).count(), 10)
        self.assertTrue(all(row['action'] == 'unchanged' for row in self.apply()))

    def test_only_editors_can_import_preview_or_edit_author_details(self):
        with self.assertRaises(PermissionDenied):
            import_careers(actor=self.student.account, directory=self.directory)
        self.apply()
        version = ContentVersion.objects.first()
        self.client.force_login(self.student.account)
        for name, args in [('dashboard', []), ('onet_import', []), ('preview', [version.pk]), ('reuse_source', [version.pk])]:
            self.assertEqual(self.client.get(reverse('maintenance:' + name, args=args)).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(reverse('maintenance:onet_import')).status_code, 302)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.author)
        self.assertEqual(csrf_client.post(reverse('maintenance:onet_import')).status_code, 403)

    def test_dashboard_filters_and_preview_do_not_publish(self):
        self.apply()
        response = self.client.get(reverse('maintenance:dashboard'), {'q': '15-1252.00', 'provider': 'onet', 'origin': 'external', 'kind': 'career', 'missing': 'yes'})
        self.assertContains(response, 'Software Developers')
        self.assertNotContains(response, '>Data Scientists</a>')
        version = ContentVersion.objects.get(title='Software Developers')
        response = self.client.get(reverse('maintenance:preview', args=[version.pk]))
        self.assertContains(response, 'positive level and weight')
        self.assertContains(response, 'CC BY 4.0')
        self.assertContains(response, 'Source ID: 15-1252.00')
        version.refresh_from_db()
        self.assertEqual(version.status, 'draft')
        self.assertFalse(version.audit_events.exists())
        self.assertIn('no-store', response.headers['Cache-Control'])
        response = self.client.get(reverse('maintenance:add_source', args=[version.pk]) + '?provider=bls')
        self.assertEqual(response.context['form'].initial['external_id'], '15-1252.00')
        self.assertIn('software-developers', response.context['form'].initial['source_url'])

    def test_source_reuse_requires_current_revision(self):
        self.apply()
        first, second = list(ContentVersion.objects.all()[:2])
        source = first.source_links.first().source
        url = reverse('maintenance:reuse_source', args=[second.pk])
        self.client.post(url, {'source': source.pk, 'usage': 'link', 'expected_revision': 999})
        self.assertFalse(second.source_links.filter(source=source).exists())
        second.refresh_from_db()
        self.assertRedirects(self.client.post(url, {'source': source.pk, 'usage': 'link', 'expected_revision': second.draft_revision}), reverse('maintenance:edit_content', args=[second.pk]))
        self.assertEqual(ReferenceSource.objects.count(), 10)

    def test_import_browser_preview_apply_and_stale_files(self):
        url = reverse('maintenance:onet_import')
        real_import = import_careers
        with patch('reference.maintenance_curation_views.import_plan', side_effect=lambda: import_plan(self.directory)), patch(
            'reference.maintenance_curation_views.import_careers', side_effect=lambda **kwargs: real_import(directory=self.directory, **kwargs)):
            response = self.client.get(url)
            self.assertContains(response, 'Import career drafts')
            self.assertFalse(ContentVersion.objects.exists())
            token = response.context['form'].initial['fingerprint']
            self.write_files('changed')
            response = self.client.post(url, {'fingerprint': token})
            self.assertContains(response, 'source files changed')
            self.assertFalse(ContentVersion.objects.exists())
            token = self.client.get(url).context['form'].initial['fingerprint']
            self.assertRedirects(self.client.post(url, {'fingerprint': token}), reverse('maintenance:dashboard'))
            self.assertEqual(ContentVersion.objects.count(), 5)
            self.assertEqual(ContentVersion.objects.filter(status='published').count(), 0)
            self.client.post(url, {'fingerprint': token})
            self.assertEqual(ContentVersion.objects.count(), 5)

    def test_stable_identity_survives_edited_source_import_metadata(self):
        self.apply()
        version = ContentVersion.objects.get(title='Software Developers')
        for source in ReferenceSource.objects.filter(version_links__version=version):
            source.raw_metadata = {}
            source.save()
        with self.assertRaisesMessage(ValidationError, 'existing draft'):
            self.apply()
        self.assertEqual(ContentVersion.objects.count(), 5)
        self.assertEqual(OnetCareerIdentity.objects.count(), 5)

    def test_mit_flow_saves_link_edition_and_prerequisites_atomically(self):
        url = reverse('maintenance:create_content') + '?preset=mit'
        data = dict(kind='resource', origin='external', title='Python foundations', body='Compass topic summary.', resource_url='https://ocw.mit.edu/courses/example/', edition='Fall 2016', prerequisites='No prior programming required.')
        response = self.client.post(url, data)
        version = ContentVersion.objects.get(kind='resource')
        self.assertRedirects(response, reverse('maintenance:edit_content', args=[version.pk]))
        self.assertEqual(version.details.provider, 'MIT OpenCourseWare')
        self.assertIn('Fall 2016', version.body)
        link = version.source_links.get()
        self.assertEqual(link.usage, 'link')
        self.assertEqual(link.source.source_version, 'Fall 2016')
        self.assertEqual(link.source.license_name, '')
        self.assertTrue(publication_issues(version))  # Coverage must be reviewed.
        data['resource_url'] = 'https://example.test/not-mit'
        self.assertEqual(self.client.post(url, data).status_code, 200)
        self.assertEqual(ContentVersion.objects.count(), 1)

    def test_changed_reflection_author_needs_fresh_originality_confirmation(self):
        item = create_content_item(actor=self.author, kind='insight')
        version = create_draft_version(actor=self.author, item_id=item.pk, title='Practice', body='A reflection.',
                                      origin='original', original_author='First author', originality_confirmed=True)
        set_field_note_profile(actor=self.author, version_id=version.pk, expected_revision=version.draft_revision,
            author_name='Changed author', author_role='', author_org='', years_experience=None,
            quote='', working_on='', learn_next='')
        version.refresh_from_db()
        self.assertEqual(version.original_author, 'Changed author')
        self.assertFalse(version.originality_confirmed)
        with self.assertRaises(ValidationError):
            publish_content_version(actor=self.author, version_id=version.pk, expected_revision=version.draft_revision)

    def test_original_note_optional_profile_and_tags_stale_edits_and_history(self):
        item = create_content_item(actor=self.author, kind='insight')
        version = create_draft_version(actor=self.author, item_id=item.pk, title='Keep practicing', body='Personal reflection.',
                                      origin='original', original_author='Student author', originality_confirmed=True)
        fields = dict(author_name='Student author', author_role='Computer science student', author_org='', years_experience=None,
                      quote='', working_on='', learn_next='', skills=[self.python])
        set_field_note_profile(actor=self.author, version_id=version.pk, expected_revision=version.draft_revision, **fields)
        with self.assertRaisesMessage(ValidationError, 'draft changed'):
            set_field_note_profile(actor=self.author, version_id=version.pk, expected_revision=1, **fields)
        version.refresh_from_db()
        self.assertIsNone(version.field_note.years_experience)
        self.assertFalse(version.field_note.is_sample)
        response = self.client.get(reverse('maintenance:field_note', args=[version.pk]))
        self.assertEqual(response.status_code, 200)
        publish_content_version(actor=self.author, version_id=version.pk, expected_revision=version.draft_revision)
        with self.assertRaisesMessage(ValidationError, 'Only draft'):
            set_field_note_profile(actor=self.author, version_id=version.pk, expected_revision=version.draft_revision, **fields)
        self.client.force_login(self.student.account)
        response = self.client.get(reverse('reference:note', args=[version.pk]))
        self.assertContains(response, 'Original personal reflection by Student author')
        self.assertContains(response, 'Python')
        self.assertNotContains(response, 'years</span>')
        self.assertContains(self.client.get(reverse('reference:notes')), 'Student author')
        self.assertContains(self.client.get(reverse('core:home')), 'Student author')


class CurationImportConcurrencyTests(TransactionTestCase):
    def test_concurrent_imports_allocate_one_identity_and_draft_per_career(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        setup_actors(self)
        with tempfile.TemporaryDirectory() as directory:
            self.directory = Path(directory)
            CurationTests.write_files(self)
            gate = Barrier(2)
            actor_id = self.author.pk

            def worker():
                close_old_connections()
                try:
                    actor = Account.objects.get(pk=actor_id)
                    gate.wait(timeout=10)
                    return [row['action'] for row in import_careers(actor=actor, dry_run=False, directory=self.directory)]
                finally:
                    connection.close()

            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [executor.submit(worker) for _ in range(2)]
                actions = [future.result(timeout=20) for future in futures]
            self.assertEqual(sorted(actions), [['create'] * 5, ['unchanged'] * 5])
            self.assertEqual(ContentVersion.objects.count(), 5)
            self.assertEqual(OnetCareerIdentity.objects.count(), 5)
            self.assertEqual(ReferenceSource.objects.count(), 10)
