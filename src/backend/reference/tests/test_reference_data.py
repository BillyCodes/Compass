"""Typed reference relations, draft revision controls, and database invariants."""
from decimal import Decimal
import uuid

from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection, IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.utils import timezone

from accounts.models import Account, AccountRole, Role
from reference.models import (
    Company, ContentDetails, ContentItem, ContentRequirement, ContentSkill,
    ContentSource, ContentVersion, ReferenceSource,
)
from reference.services import (
    attach_source, clear_content_details, create_company, create_content_item,
    create_draft_version, create_reference_source, detach_source,
    remove_requirement, remove_skill_mapping, set_content_details,
    set_requirement, set_skill_mapping,
)
from skills.models import Skill


class ReferenceDataTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.editor = Account.objects.create_user("reference.data.editor@example.test")
        cls.student = Account.objects.create_user("reference.data.student@example.test")
        cls.admin = Account.objects.create_user("reference.data.admin@example.test")
        for account, role in [(cls.editor, "maintainer"), (cls.student, "student"), (cls.admin, "administrator")]:
            AccountRole.objects.create(account=account, role=Role.objects.get(role_name=role))
        cls.skill = Skill.objects.create(skill_name="Reference SQL")
        cls.company = create_company(actor=cls.editor, company_name="Sample Company", industry="Technology")
        cls.source = create_reference_source(actor=cls.editor, source_title="Sample source", source_url_or_identifier="dataset:sample-v1")
        cls.versions = {}
        for kind in ("career", "job", "course", "resource", "insight"):
            item = create_content_item(actor=cls.editor, kind=kind)
            cls.versions[kind] = create_draft_version(actor=cls.editor, item_id=item.pk, title=f"Sample {kind}", body="Sample draft")

    def revision(self, kind):
        self.versions[kind].refresh_from_db()
        return self.versions[kind].draft_revision

    def requirement(self, kind="career", **overrides):
        fields = dict(actor=self.editor, version_id=self.versions[kind].pk, skill_id=self.skill.pk,
                      required_level=3, mandatory=True, weight="1.25", expected_revision=self.revision(kind))
        fields.update(overrides)
        return set_requirement(**fields)

    def mapping(self, kind="course", **overrides):
        fields = dict(actor=self.editor, version_id=self.versions[kind].pk, skill_id=self.skill.pk,
                      coverage_level=2, expected_revision=self.revision(kind))
        fields.update(overrides)
        return set_skill_mapping(**fields)

    def details(self, kind="job", **overrides):
        fields = dict(actor=self.editor, version_id=self.versions[kind].pk, expected_revision=self.revision(kind))
        fields.update(overrides)
        return set_content_details(**fields)

    def attach(self, kind="career", **overrides):
        fields = dict(actor=self.editor, version_id=self.versions[kind].pk, source_id=self.source.pk,
                      expected_revision=self.revision(kind))
        fields.update(overrides)
        return attach_source(**fields)

    def test_company_and_source_validate_and_trim_text(self):
        company = create_company(actor=self.editor, company_name="  Example  ", industry="  Education ")
        self.assertEqual((company.company_name, company.industry), ("Example", "Education"))
        source = create_reference_source(actor=self.admin, source_title=" Source ", source_url_or_identifier=" ISBN:sample ")
        self.assertEqual(source.source_url_or_identifier, "ISBN:sample")
        self.assertTrue(timezone.is_aware(source.collected_at))
        for call in [lambda: create_company(actor=self.editor, company_name=" "),
                     lambda: create_reference_source(actor=self.editor, source_title="Source", source_url_or_identifier=" ")]:
            with self.assertRaises(ValidationError):
                call()

    def test_unauthorized_accounts_cannot_create_or_attach_reference_data(self):
        for actor in (self.student, AnonymousUser()):
            for operation in [lambda: create_company(actor=actor, company_name="Denied"),
                              lambda: create_reference_source(actor=actor, source_title="Denied", source_url_or_identifier="Denied"),
                              lambda: self.attach(actor=actor), lambda: self.requirement(actor=actor),
                              lambda: self.mapping(actor=actor), lambda: self.details(actor=actor)]:
                with self.assertRaises(PermissionDenied):
                    operation()

    def test_disabled_editor_cannot_write(self):
        self.editor.is_active = False
        with self.assertRaises(PermissionDenied):
            self.requirement()

    def test_business_administrator_can_write_but_staff_flag_alone_cannot(self):
        self.requirement(actor=self.admin)
        self.student.is_staff = True
        self.student.is_superuser = True
        with self.assertRaises(PermissionDenied):
            self.mapping(actor=self.student)

    def test_source_attachment_is_unique_and_noop_does_not_bump_revision(self):
        one = self.attach()
        two = self.attach()
        self.assertEqual(one.pk, two.pk)
        self.assertEqual(self.revision("career"), 2)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ContentSource.objects.create(version=self.versions["career"], source=self.source)

    def test_same_source_can_support_multiple_content_versions(self):
        self.attach("career")
        self.attach("job")
        self.assertEqual(self.source.version_links.count(), 2)

    def test_source_and_version_deletion_are_protected_when_linked(self):
        self.attach()
        for obj in (self.source, self.versions["career"]):
            with self.assertRaises(ProtectedError):
                obj.delete()

    def test_requirements_upsert_per_skill_and_increment_revision(self):
        one = self.requirement()
        two = self.requirement(required_level=5, weight="0", mandatory=False)
        self.assertEqual(one.pk, two.pk)
        self.assertEqual(two.weight, Decimal("0"))
        self.assertEqual(self.revision("career"), 3)
        self.assertEqual(ContentRequirement.objects.count(), 1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ContentRequirement.objects.create(version=self.versions["career"], skill=self.skill, kind="career", required_level=1)

    def test_requirement_kinds_are_career_and_job_only(self):
        for kind in ("career", "job"):
            self.requirement(kind)
        for kind in ("course", "resource", "insight"):
            with self.assertRaises(ValidationError):
                self.requirement(kind)
            self.assertEqual(self.revision(kind), 1)

    def test_requirement_level_weight_and_mandatory_validation(self):
        for change in ({"required_level": -1}, {"required_level": 6}, {"required_level": True},
                       {"required_level": 2.5}, {"mandatory": "false"}, {"weight": "-1"},
                       {"weight": "NaN"}, {"weight": "Infinity"}, {"weight": "0.00001"}):
            with self.subTest(change=change), self.assertRaises(ValidationError):
                self.requirement(**change)
        self.assertFalse(ContentRequirement.objects.exists())
        self.assertEqual(self.revision("career"), 1)

    def test_learning_mappings_support_course_and_resource_only(self):
        for kind in ("course", "resource"):
            row = self.mapping(kind)
            self.assertEqual(row.kind, kind)
        for kind in ("career", "job", "insight"):
            with self.assertRaises(ValidationError):
                self.mapping(kind)

    def test_learning_mapping_upsert_and_bounds(self):
        first = self.mapping()
        second = self.mapping(coverage_level=5)
        self.assertEqual(first.pk, second.pk)
        for level in (-1, 6, True, "3"):
            with self.subTest(level=level), self.assertRaises(ValidationError):
                self.mapping(coverage_level=level)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ContentSkill.objects.create(version=self.versions["course"], skill=self.skill, kind="course", coverage_level=1)

    def test_retired_skill_cannot_receive_requirements_or_mappings(self):
        self.skill.status = "retired"
        self.skill.save(update_fields=["status"])
        for operation in (self.requirement, self.mapping):
            with self.assertRaises(ValidationError):
                operation()
        self.assertEqual(self.revision("career"), 1)
        self.assertEqual(self.revision("course"), 1)

    def test_details_are_optional_one_to_one_and_updates_reuse_pk(self):
        self.assertFalse(ContentDetails.objects.exists())
        first = self.details(company_id=self.company.pk, location=" Remote ")
        second = self.details(location="On-site")
        self.assertEqual(first.pk, second.pk)
        self.assertIsNone(second.company_id)  # Full replacement clears omitted fields.
        self.assertEqual(second.location, "On-site")
        self.assertEqual(self.revision("job"), 3)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ContentDetails.objects.create(version=self.versions["job"], kind="job")

    def test_job_details_allow_optional_company_and_expiry(self):
        self.details(location="Remote", expires_at=timezone.now())
        self.details(company_id=self.company.pk)
        with self.assertRaises(ProtectedError):
            self.company.delete()

    def test_course_and_resource_details_validate_price_and_currency(self):
        row = self.details("course", course_code="CSC 310", credits="3", provider="JSU", cost_amount="0", currency="usd", resource_url="https://example.test/course")
        self.assertEqual(row.currency, "USD")
        self.assertEqual(row.credits, Decimal("3"))
        self.details("resource", provider="Example", resource_url="https://example.test/resource", cost_amount="12.50", currency="USD")

    def test_type_specific_fields_are_rejected_on_wrong_content_kind(self):
        for kind, fields in [("career", {"company_id": self.company.pk}), ("course", {"location": "Remote"}),
                             ("resource", {"course_code": "CSC 310"}), ("job", {"credits": "3"}),
                             ("insight", {"provider": "Example"}), ("career", {"cost_amount": "0", "currency": "USD"})]:
            with self.subTest(kind=kind, fields=fields), self.assertRaises(ValidationError):
                self.details(kind, **fields)
            self.assertEqual(self.revision(kind), 1)

    def test_details_numeric_currency_and_url_validation(self):
        for fields in ({"cost_amount": "-1", "currency": "USD"}, {"credits": "NaN"},
                       {"cost_amount": "Infinity", "currency": "USD"}, {"cost_amount": "10"},
                       {"currency": "USD"}, {"cost_amount": "10", "currency": "US"},
                       {"resource_url": "javascript:alert(1)"}, {"resource_url": "ftp://example.test/file"},
                       {"company_id": uuid.uuid4()}, {"provider": None}):
            with self.subTest(fields=fields), self.assertRaises(ValidationError):
                self.details("course", **fields)
        self.assertFalse(ContentDetails.objects.exists())
        self.assertEqual(self.revision("course"), 1)

    def test_all_child_changes_reject_stale_revisions(self):
        self.attach()
        with self.assertRaises(ValidationError):
            self.requirement(expected_revision=1)
        self.assertEqual(ContentRequirement.objects.count(), 0)
        for revision in (0, True, 1.5, "2"):
            with self.assertRaises(ValidationError):
                self.attach(expected_revision=revision)

    def test_retired_item_blocks_related_draft_edits(self):
        item = self.versions["career"].item
        item.retired_at = timezone.now()
        item.save(update_fields=["retired_at"])
        with self.assertRaises(ValidationError):
            self.attach()

    def test_published_versions_block_all_related_edit_and_remove_services(self):
        for kind in self.versions:
            row = self.versions[kind]
            ContentVersion.objects.filter(pk=row.pk).update(status="published", published_by=self.editor, published_at=timezone.now())
        operations = [self.attach, self.requirement, self.mapping, self.details,
                      lambda: detach_source(actor=self.editor, version_id=self.versions["career"].pk, source_id=self.source.pk, expected_revision=1),
                      lambda: remove_requirement(actor=self.editor, version_id=self.versions["career"].pk, skill_id=self.skill.pk, expected_revision=1),
                      lambda: remove_skill_mapping(actor=self.editor, version_id=self.versions["course"].pk, skill_id=self.skill.pk, expected_revision=1),
                      lambda: clear_content_details(actor=self.editor, version_id=self.versions["job"].pk, expected_revision=1)]
        for operation in operations:
            with self.assertRaises(ValidationError):
                operation()

    def test_removing_draft_links_increments_revision_only_for_changes(self):
        self.attach()
        args = dict(actor=self.editor, version_id=self.versions["career"].pk, source_id=self.source.pk, expected_revision=2)
        self.assertTrue(detach_source(**args))
        args["expected_revision"] = 3
        self.assertFalse(detach_source(**args))
        self.assertEqual(self.revision("career"), 3)
        self.requirement()
        self.assertTrue(remove_requirement(actor=self.editor, version_id=self.versions["career"].pk, skill_id=self.skill.pk, expected_revision=4))
        self.mapping()
        self.assertTrue(remove_skill_mapping(actor=self.editor, version_id=self.versions["course"].pk, skill_id=self.skill.pk, expected_revision=2))
        self.details()
        self.assertTrue(clear_content_details(actor=self.editor, version_id=self.versions["job"].pk, expected_revision=2))

    def test_referenced_skills_are_protected_from_deletion(self):
        self.requirement()
        self.mapping()
        with self.assertRaises(ProtectedError):
            self.skill.delete()

    def test_each_typed_child_has_a_database_composite_foreign_key(self):
        for table in ("content_requirement", "content_skill", "content_details"):
            with connection.cursor() as cursor:
                constraints = connection.introspection.get_constraints(cursor, table)
            constraint = constraints[f"{table}_version_kind_fk"]
            self.assertEqual(constraint["columns"], ["version_id", "kind"])
            self.assertEqual(constraint["foreign_key"][0], "content_version")

    def test_direct_writes_cannot_mismatch_parent_version_kind(self):
        rows = [(self.requirement(), "job"), (self.mapping(), "resource"), (self.details(), "course")]
        for row, wrong_kind in rows:
            with self.subTest(model=type(row).__name__), self.assertRaises(IntegrityError), transaction.atomic():
                type(row).objects.filter(pk=row.pk).update(kind=wrong_kind)

    def test_direct_writes_cannot_create_requirements_or_mappings_on_wrong_kind(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            ContentRequirement.objects.create(version=self.versions["course"], kind="course", skill=self.skill, required_level=2)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ContentSkill.objects.create(version=self.versions["career"], kind="career", skill=self.skill, coverage_level=2)

    def test_database_enforces_levels_and_nonnegative_weight(self):
        requirement = self.requirement()
        mapping = self.mapping()
        for model, pk, values in [(ContentRequirement, requirement.pk, {"required_level": 6}),
                                  (ContentRequirement, requirement.pk, {"weight": -1}),
                                  (ContentSkill, mapping.pk, {"coverage_level": 6})]:
            with self.assertRaises(IntegrityError), transaction.atomic():
                model.objects.filter(pk=pk).update(**values)

    def test_database_rejects_numeric_nan_even_when_model_validation_is_bypassed(self):
        requirement = self.requirement()
        details = self.details("course", credits="3", cost_amount="10", currency="USD")
        for table, column, key, pk in [("content_requirement", "weight", "requirement_id", requirement.pk),
                                       ("content_details", "credits", "version_id", details.pk),
                                       ("content_details", "cost_amount", "version_id", details.pk)]:
            with self.subTest(column=column), self.assertRaises(IntegrityError), transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(f"UPDATE {table} SET {column} = 'NaN'::numeric WHERE {key} = %s", [pk])

    def test_database_rejects_wrong_detail_fields_and_unpaired_price(self):
        row = self.details("course")
        for values in ({"company": self.company}, {"location": "Remote"}, {"cost_amount": 10}, {"credits": -1}):
            with self.subTest(values=values), self.assertRaises(IntegrityError), transaction.atomic():
                ContentDetails.objects.filter(pk=row.pk).update(**values)

    def test_model_validation_rejects_typed_child_mismatch(self):
        rows = [
            ContentRequirement(version=self.versions["career"], kind="job", skill=self.skill, required_level=2),
            ContentSkill(version=self.versions["course"], kind="resource", skill=self.skill, coverage_level=2),
            ContentDetails(version=self.versions["job"], kind="career"),
        ]
        for row in rows:
            with self.subTest(model=type(row).__name__), self.assertRaises(ValidationError) as caught:
                row.full_clean()
            self.assertIn("kind", caught.exception.message_dict)

    def test_all_six_agreed_levels_are_supported_for_requirements_and_coverage(self):
        for level in range(6):
            self.assertEqual(self.requirement(required_level=level).required_level, level)
            self.assertEqual(self.mapping(coverage_level=level).coverage_level, level)
