"""Independent revision-specific review, publication, and database immutability."""
from datetime import timedelta

from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection, IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.utils import timezone

from accounts.models import Account, AccountRole, Role
from reference.models import ContentDetails, ContentItem, ContentRequirement, ContentReview, ContentSkill, ContentSource, ContentVersion
from reference.services import (
    attach_source, available_content_versions, create_company, create_content_item,
    create_draft_version, create_reference_source, publish_content_version,
    retire_content_version, review_content_version, set_content_details,
    set_requirement, set_skill_mapping, update_draft_version,
)
from reference.tests.factories import prepare_for_publication, publish_complete_version
from skills.models import Skill


class PublicationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.author = Account.objects.create_user("publish.author@example.test")
        cls.reviewer = Account.objects.create_user("publish.reviewer@example.test")
        cls.admin = Account.objects.create_user("publish.admin@example.test")
        cls.student = Account.objects.create_user("publish.student@example.test")
        for actor, role in [(cls.author,"maintainer"),(cls.reviewer,"maintainer"),(cls.admin,"administrator"),(cls.student,"student")]:
            AccountRole.objects.create(account=actor, role=Role.objects.get(role_name=role))

    def draft(self, kind="career", complete=True):
        item = create_content_item(actor=self.author, kind=kind)
        version = create_draft_version(actor=self.author, item_id=item.pk, title=f"Sample {kind}", body="Synthetic reference body")
        return prepare_for_publication(version,self.author) if complete else version

    def review(self, version, decision="approved", actor=None):
        version.refresh_from_db()
        return review_content_version(actor=actor or self.reviewer, version_id=version.pk,
                                      expected_revision=version.draft_revision, decision=decision)

    def publish(self, version, actor=None):
        version.refresh_from_db()
        return publish_content_version(actor=actor or self.author, version_id=version.pk,
                                       expected_revision=version.draft_revision)

    def test_all_content_kinds_publish_after_independent_approval(self):
        for kind in ("career","job","course","resource","insight"):
            version = self.draft(kind)
            review = self.review(version)
            self.assertEqual(review.reviewed_revision,version.draft_revision)
            published = self.publish(version)
            self.assertEqual(published.status,"published")
            self.assertEqual(published.published_by,self.author)
            self.assertIsNotNone(published.published_at)
            self.assertTrue(available_content_versions().filter(pk=version.pk).exists())

    def test_author_cannot_approve_own_draft(self):
        version = self.draft()
        with self.assertRaises(ValidationError):
            self.review(version,actor=self.author)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ContentReview.objects.create(version=version, reviewer=self.author, reviewed_revision=version.draft_revision, decision="approved")

    def test_students_anonymous_and_staff_only_cannot_review_or_publish(self):
        version = self.draft()
        self.student.is_staff = True
        self.student.is_superuser = True
        for actor in (self.student,AnonymousUser()):
            with self.assertRaises(PermissionDenied):
                review_content_version(actor=actor, version_id=version.pk, expected_revision=version.draft_revision, decision="approved")
            with self.assertRaises(PermissionDenied):
                publish_content_version(actor=actor, version_id=version.pk, expected_revision=version.draft_revision)

    def test_admin_is_allowed_to_review_and_publish(self):
        version = self.draft()
        self.review(version,actor=self.admin)
        self.assertEqual(self.publish(version,actor=self.admin).published_by,self.admin)

    def test_missing_or_requested_changes_approval_blocks_publication(self):
        version = self.draft()
        with self.assertRaises(ValidationError):
            self.publish(version)
        self.review(version,decision="changes_requested")
        with self.assertRaises(ValidationError):
            self.publish(version)
        version.refresh_from_db()
        self.assertEqual(version.status,"draft")
        self.assertIsNone(version.published_at)

    def test_latest_decision_wins_and_reviews_remain_append_only(self):
        version = self.draft()
        one = self.review(version)
        two = self.review(version,decision="changes_requested",actor=self.admin)
        self.assertGreater(two.reviewed_at,one.reviewed_at)
        with self.assertRaises(ValidationError):
            self.publish(version)
        self.review(version)
        self.publish(version)
        self.assertEqual(version.reviews.count(),3)
        for operation in (lambda: ContentReview.objects.filter(pk=one.pk).update(decision="changes_requested"), lambda: one.delete()):
            with self.assertRaises(IntegrityError), transaction.atomic():
                operation()

    def test_disabled_or_deauthorized_reviewer_approval_no_longer_publishes(self):
        version = self.draft()
        self.review(version)
        self.reviewer.is_active = False
        self.reviewer.save(update_fields=["is_active"])
        with self.assertRaises(ValidationError):
            self.publish(version)
        self.reviewer.is_active = True
        self.reviewer.save(update_fields=["is_active"])
        self.reviewer.role_assignments.all().delete()
        with self.assertRaises(ValidationError):
            self.publish(version)

    def test_review_does_not_change_revision_and_stale_review_is_rejected(self):
        version = self.draft()
        revision = version.draft_revision
        self.review(version)
        version.refresh_from_db()
        self.assertEqual(version.draft_revision,revision)
        update_draft_version(actor=self.author,version_id=version.pk,expected_revision=revision,title="Updated",body="Updated body")
        with self.assertRaises(ValidationError):
            review_content_version(actor=self.reviewer,version_id=version.pk,expected_revision=revision,decision="approved")
        with self.assertRaises(ValidationError):
            self.publish(version)

    def test_direct_draft_text_write_invalidates_approval(self):
        version = self.draft()
        self.review(version)
        old_revision = version.draft_revision
        ContentVersion.objects.filter(pk=version.pk).update(body="Direct edit")
        version.refresh_from_db()
        self.assertEqual(version.draft_revision,old_revision+1)
        with self.assertRaises(ValidationError):
            self.publish(version)

    def test_each_direct_child_write_invalidates_approval(self):
        for kind, model, values in [("career",ContentRequirement,{"required_level":4}),
                                     ("course",ContentSkill,{"coverage_level":4}),
                                     ("course",ContentDetails,{"provider":"New provider"})]:
            version = self.draft(kind)
            self.review(version)
            old_revision = version.draft_revision
            model.objects.filter(version=version).update(**values)
            version.refresh_from_db()
            self.assertEqual(version.draft_revision,old_revision+1)
            with self.assertRaises(ValidationError):
                self.publish(version)

    def test_source_changes_and_detachment_invalidate_approval(self):
        version = self.draft()
        self.review(version)
        source = version.source_links.get().source
        old_revision = version.draft_revision
        type(source).objects.filter(pk=source.pk).update(source_title="Corrected citation")
        version.refresh_from_db()
        self.assertEqual(version.draft_revision,old_revision+1)
        with self.assertRaises(ValidationError):
            self.publish(version)
        self.review(version)
        ContentSource.objects.filter(version=version).delete()
        with self.assertRaises(ValidationError):
            self.publish(version)

    def test_company_changes_invalidate_draft_review(self):
        version = self.draft("job")
        company = create_company(actor=self.author,company_name="Example")
        set_content_details(actor=self.author,version_id=version.pk,expected_revision=version.draft_revision,company_id=company.pk)
        self.review(version)
        type(company).objects.filter(pk=company.pk).update(company_name="Renamed")
        with self.assertRaises(ValidationError):
            self.publish(version)

    def test_career_publication_requires_sources_and_positive_weight(self):
        version = self.draft(complete=False)
        self.review(version)
        with self.assertRaisesMessage(ValidationError,"source"):
            self.publish(version)
        source = create_reference_source(actor=self.author,source_title="Source",source_url_or_identifier="fixture:no-weight")
        attach_source(actor=self.author,version_id=version.pk,source_id=source.pk,expected_revision=version.draft_revision)
        self.review(version)
        with self.assertRaisesMessage(ValidationError,"requirements"):
            self.publish(version)
        skill = Skill.objects.create(skill_name="Zero-weight skill")
        set_requirement(actor=self.author,version_id=version.pk,skill_id=skill.pk,required_level=2,mandatory=False,weight="0",expected_revision=version.draft_revision)
        self.review(version)
        with self.assertRaisesMessage(ValidationError,"positive weight"):
            self.publish(version)

    def test_learning_publication_requires_positive_coverage_and_identifying_details(self):
        for kind, field, missing in [("course","course_code","course code"),("resource","resource_url","URL")]:
            version = self.draft(kind)
            ContentDetails.objects.filter(version=version).update(**{field:""})
            self.review(version)
            with self.assertRaisesMessage(ValidationError,missing):
                self.publish(version)
        version = self.draft("course")
        ContentSkill.objects.filter(version=version).update(coverage_level=0)
        self.review(version)
        with self.assertRaisesMessage(ValidationError,"positive skill coverage"):
            self.publish(version)

    def test_expired_jobs_and_retired_skills_cannot_publish(self):
        version = self.draft("job")
        set_content_details(actor=self.author,version_id=version.pk,expected_revision=version.draft_revision,expires_at=timezone.now()-timedelta(days=1))
        self.review(version)
        with self.assertRaisesMessage(ValidationError,"Expired"):
            self.publish(version)
        version = self.draft()
        self.review(version)
        Skill.objects.filter(pk=version.requirements.get().skill_id).update(status="retired")
        with self.assertRaisesMessage(ValidationError,"Retired skills"):
            self.publish(version)

    def test_direct_sql_cannot_publish_without_approval_or_create_published_version(self):
        version = self.draft()
        with self.assertRaises(IntegrityError), transaction.atomic():
            ContentVersion.objects.filter(pk=version.pk).update(status="published",published_by=self.author,published_at=timezone.now())
        with self.assertRaises(IntegrityError), transaction.atomic():
            ContentVersion.objects.create(item=version.item,kind="career",version_no=2,title="Bypass",body="Bypass",created_by=self.author,status="published",published_by=self.author,published_at=timezone.now())

    def test_published_core_content_cannot_be_modified_or_deleted(self):
        version = self.draft()
        self.review(version)
        self.publish(version)
        for values in ({"body":"Changed"},{"title":"Changed"},{"draft_revision":100},{"status":"draft"},{"published_by":self.admin}):
            with self.assertRaises(IntegrityError), transaction.atomic():
                ContentVersion.objects.filter(pk=version.pk).update(**values)
        # SQL reaches the deletion trigger directly rather than ORM PROTECT checks.
        with self.assertRaises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute("DELETE FROM content_version WHERE version_id=%s",[version.pk])

    def test_all_published_child_types_reject_insert_update_and_delete(self):
        career = self.draft()
        course = self.draft("course")
        for version in (career,course):
            self.review(version)
            self.publish(version)
        rows = [career.requirements.get(),course.skill_mappings.get(),course.details,career.source_links.get()]
        for row in rows:
            if isinstance(row,ContentRequirement): values={"required_level":5}
            elif isinstance(row,ContentSkill): values={"coverage_level":5}
            elif isinstance(row,ContentDetails): values={"provider":"Changed"}
            else: values={"source":create_reference_source(actor=self.author,source_title="New",source_url_or_identifier="new")}
            for operation in (lambda row=row,values=values: type(row).objects.filter(pk=row.pk).update(**values), lambda row=row: row.delete()):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    operation()
        extra = create_reference_source(actor=self.author,source_title="Extra",source_url_or_identifier="extra")
        with self.assertRaises(IntegrityError), transaction.atomic():
            ContentSource.objects.create(version=career,source=extra)

    def test_shared_source_and_company_are_frozen_after_publication(self):
        version = self.draft("job")
        company = create_company(actor=self.author,company_name="Frozen company")
        set_content_details(actor=self.author,version_id=version.pk,expected_revision=version.draft_revision,company_id=company.pk)
        self.review(version)
        self.publish(version)
        source = version.source_links.get().source
        for obj, values in [(company,{"company_name":"Changed"}),(source,{"source_title":"Changed"})]:
            with self.assertRaises(IntegrityError), transaction.atomic():
                type(obj).objects.filter(pk=obj.pk).update(**values)

    def test_retirement_preserves_history_and_blocks_republication(self):
        version = self.draft()
        self.review(version)
        self.publish(version)
        self.assertEqual(retire_content_version(actor=self.author,version_id=version.pk).status,"retired")
        self.assertFalse(available_content_versions().filter(pk=version.pk).exists())
        with self.assertRaises(IntegrityError), transaction.atomic():
            ContentVersion.objects.filter(pk=version.pk).update(status="published")
        self.assertEqual(version.requirements.count(),1)

    def test_successor_version_does_not_change_published_edition(self):
        one = self.draft()
        self.review(one)
        self.publish(one)
        two = create_draft_version(actor=self.author,item_id=one.item_id,title="Successor",body="New draft")
        self.assertEqual(two.version_no,2)
        one.refresh_from_db()
        self.assertEqual(one.title,"Sample career")
        self.assertEqual(one.status,"published")

    def test_only_available_versions_are_listed(self):
        draft = self.draft("insight")
        self.assertFalse(available_content_versions().filter(pk=draft.pk).exists())
        self.review(draft)
        self.publish(draft)
        ContentItem.objects.filter(pk=draft.item_id).update(retired_at=timezone.now())
        self.assertFalse(available_content_versions(kind="insight").filter(pk=draft.pk).exists())

    def test_review_invalid_decisions_revisions_and_protected_attribution(self):
        version = self.draft()
        with self.assertRaises(ValidationError):
            self.review(version,decision="unknown")
        review = self.review(version)
        with self.assertRaises(ProtectedError):
            self.reviewer.delete()
        with self.assertRaises(IntegrityError), transaction.atomic():
            ContentReview.objects.create(version=version,reviewer=self.reviewer,reviewed_revision=1,decision="approved")

    def test_latest_review_timestamps_are_strictly_monotonic(self):
        version = self.draft()
        one = self.review(version)
        two = self.review(version)
        self.assertGreater(two.reviewed_at,one.reviewed_at)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ContentReview.objects.create(version=version,reviewer=self.reviewer,reviewed_revision=version.draft_revision,decision="approved",reviewed_at=one.reviewed_at)

    def test_shared_source_change_updates_all_drafts_and_rolls_back_if_one_is_published(self):
        one = self.draft("insight")
        two = self.draft("insight")
        source = one.source_links.get().source
        attach_source(actor=self.author,version_id=two.pk,source_id=source.pk,expected_revision=two.draft_revision)
        one.refresh_from_db()
        two.refresh_from_db()
        before = (one.draft_revision,two.draft_revision)
        type(source).objects.filter(pk=source.pk).update(source_title="Shared corrected source")
        one.refresh_from_db()
        two.refresh_from_db()
        self.assertEqual((one.draft_revision,two.draft_revision),(before[0]+1,before[1]+1))
        self.review(one)
        self.publish(one)
        before_two = two.draft_revision
        with self.assertRaises(IntegrityError), transaction.atomic():
            type(source).objects.filter(pk=source.pk).update(source_title="Forbidden shared change")
        two.refresh_from_db()
        source.refresh_from_db()
        self.assertEqual(two.draft_revision,before_two)
        self.assertEqual(source.source_title,"Shared corrected source")

    def test_review_cannot_be_added_to_published_or_retired_item(self):
        version = self.draft()
        self.review(version)
        self.publish(version)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ContentReview.objects.create(version=version,reviewer=self.reviewer,reviewed_revision=version.draft_revision,decision="approved")
        other = self.draft("insight")
        ContentItem.objects.filter(pk=other.item_id).update(retired_at=timezone.now())
        with self.assertRaises(ValidationError):
            self.review(other)

    def test_publication_revalidates_url_syntax_after_direct_draft_edit(self):
        version = self.draft("resource")
        ContentDetails.objects.filter(version=version).update(resource_url="http://")
        self.review(version)
        with self.assertRaises(ValidationError):
            self.publish(version)

    def test_publication_rejects_whitespace_only_citation_fields(self):
        version = self.draft("insight")
        source = version.source_links.get().source
        type(source).objects.filter(pk=source.pk).update(source_title="   ")
        self.review(version)
        with self.assertRaisesMessage(ValidationError,"Source titles"):
            self.publish(version)
