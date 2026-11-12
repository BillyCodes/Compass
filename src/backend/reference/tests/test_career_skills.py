"""Career-specific selections enrich catalogs without changing edition history."""
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from comparisons.tests.factories import setup_actors
from reference.career_skills import BASE_SKILLS, EXTRAS, selected_examples, version_suggestions
from reference.models import ContentVersion, ReferenceSource
from reference.onet_import import import_careers, import_plan
from reference.services import publish_content_version, set_requirement, update_draft_version
from skills.models import Skill


class CareerSkillSelectionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        setup_actors(cls)

    def setUp(self):
        self.client.force_login(self.author)

    def test_every_career_has_ten_additional_exact_source_matches(self):
        for row in import_plan():
            with self.subTest(code=row['code']):
                raw_names = {example['Workplace Example'] for example in row['examples']}
                self.assertEqual(len(EXTRAS[row['code']]), 10)
                self.assertTrue(set(EXTRAS[row['code']]).issubset(raw_names))
                self.assertFalse(set(EXTRAS[row['code']]) & set(BASE_SKILLS))
                self.assertEqual(len(row['skills']), 16)

    def test_unchanged_published_editions_can_receive_catalog_additions_without_history_changes(self):
        base_names = {value[0] for value in BASE_SKILLS.values()}
        with patch('reference.onet_import.selected_examples', side_effect=lambda code, rows: [row for row in selected_examples(code, rows) if row['skill'] in base_names]):
            import_careers(actor=self.author, dry_run=False)
        self.assertEqual(Skill.objects.count(), 6)
        snapshots = {}
        for version in ContentVersion.objects.all():
            set_requirement(actor=self.author, version_id=version.pk, expected_revision=version.draft_revision,
                            skill_id=self.python.pk, required_level=2, mandatory=False, weight='1')
            version.refresh_from_db()
            publish_content_version(actor=self.author, version_id=version.pk, expected_revision=version.draft_revision)
            snapshots[version.pk] = (version.title, version.body, version.draft_revision)
        sources = list(ReferenceSource.objects.order_by('pk').values())
        result = import_careers(actor=self.author, dry_run=False)
        self.assertTrue(all(row['action'] == 'unchanged' for row in result))
        self.assertGreater(Skill.objects.count(), 16)
        self.assertEqual(ContentVersion.objects.count(), 5)
        self.assertEqual(ContentVersion.objects.filter(status='published').count(), 5)
        for version in ContentVersion.objects.all():
            self.assertEqual((version.title, version.body, version.draft_revision), snapshots[version.pk])
            self.assertEqual(version.requirements.count(), 1)
            self.assertEqual(len(version_suggestions(version)), 16)
        self.assertEqual(list(ReferenceSource.objects.order_by('pk').values()), sources)
        count = Skill.objects.count()
        import_careers(actor=self.author, dry_run=False)
        self.assertEqual(Skill.objects.count(), count)

    def test_picker_defaults_to_career_associations_and_supports_search_demand_and_all_catalog(self):
        import_careers(actor=self.author, dry_run=False)
        security = ContentVersion.objects.get(title='Information Security Analysts')
        url = reverse('maintenance:add_requirement', args=[security.pk])
        response = self.client.get(url)
        choices = response.context['form'].fields['skill'].queryset
        self.assertEqual(choices.count(), 16)
        self.assertTrue(choices.filter(skill_name='Wireshark').exists())
        self.assertFalse(choices.filter(skill_name='React').exists())
        self.assertContains(response, 'MITRE ATT&amp;CK software')
        self.assertContains(response, 'In demand: Yes')
        response = self.client.get(url, {'catalog': 'all', 'q': 'React'})
        self.assertTrue(response.context['form'].fields['skill'].queryset.filter(skill_name='React').exists())
        response = self.client.get(url, {'q': 'Microsoft PowerShell', 'demand': 'yes'})
        self.assertEqual(list(response.context['form'].fields['skill'].queryset.values_list('skill_name', flat=True)), ['PowerShell'])
        response = self.client.get(url, {'catalog': 'all', 'q': 'Microsoft PowerShell'})
        self.assertEqual(list(response.context['form'].fields['skill'].queryset.values_list('skill_name', flat=True)), ['PowerShell'])
        response = self.client.get(url, {'q': 'does-not-exist'})
        self.assertContains(response, 'No selected associations match')
        self.assertFalse(response.context['form'].fields['skill'].queryset.exists())
        self.assertFalse(security.requirements.exists())

    def test_new_requirement_still_needs_manual_values_and_current_revision(self):
        import_careers(actor=self.author, dry_run=False)
        version = ContentVersion.objects.get(title='Data Scientists')
        url = reverse('maintenance:add_requirement', args=[version.pk])
        skill = Skill.objects.get(skill_name='PyTorch')
        update_draft_version(actor=self.author, version_id=version.pk, expected_revision=version.draft_revision,
                             title=version.title, body='Editorial work preserved.')
        data = {'skill': skill.pk, 'required_level': 2, 'weight': '1', 'expected_revision': version.draft_revision}
        response = self.client.post(url, data)
        self.assertContains(response, 'draft changed')
        self.assertFalse(version.requirements.exists())
        version.refresh_from_db()
        data['expected_revision'] = version.draft_revision
        self.assertRedirects(self.client.post(url, data), reverse('maintenance:edit_content', args=[version.pk]))
        self.assertEqual(version.requirements.get().skill, skill)
        version.refresh_from_db()
        self.assertEqual(version.body, 'Editorial work preserved.')
        self.assertEqual(version.status, 'draft')

    def test_dry_run_does_not_add_catalog_entries(self):
        import_careers(actor=self.author)
        self.assertEqual(Skill.objects.count(), 2)  # Fixture skills only.
        self.assertFalse(ContentVersion.objects.exists())
