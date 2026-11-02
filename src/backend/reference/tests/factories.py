"""Complete synthetic reference data through real services, not publication bypasses."""
from skills.models import Skill
from reference.models import ContentKind
from reference.services import (
    attach_source, create_reference_source, publish_content_version,
    review_content_version, set_content_details, set_requirement, set_skill_mapping,
)


def prepare_for_publication(version, author):
    source = create_reference_source(actor=author, source_title="Synthetic reference", source_url_or_identifier=f"fixture:{version.pk}")
    version.refresh_from_db()
    attach_source(actor=author, version_id=version.pk, source_id=source.pk, expected_revision=version.draft_revision)
    if version.kind in (ContentKind.CAREER, ContentKind.JOB):
        skill, _ = Skill.objects.get_or_create(skill_name="Publication fixture skill")
        version.refresh_from_db()
        set_requirement(actor=author, version_id=version.pk, skill_id=skill.pk, required_level=2,
                        mandatory=False, weight="1", expected_revision=version.draft_revision)
    elif version.kind in (ContentKind.COURSE, ContentKind.RESOURCE):
        skill, _ = Skill.objects.get_or_create(skill_name="Publication fixture skill")
        version.refresh_from_db()
        set_skill_mapping(actor=author, version_id=version.pk, skill_id=skill.pk, coverage_level=2,
                          expected_revision=version.draft_revision)
        version.refresh_from_db()
        fields = {"course_code":"TEST 101"} if version.kind == ContentKind.COURSE else {"resource_url":"https://example.test/learning"}
        set_content_details(actor=author, version_id=version.pk, expected_revision=version.draft_revision, **fields)
    version.refresh_from_db()
    return version


def publish_complete_version(version, author, reviewer):
    prepare_for_publication(version, author)
    review_content_version(actor=reviewer, version_id=version.pk, expected_revision=version.draft_revision, decision="approved")
    return publish_content_version(actor=author, version_id=version.pk, expected_revision=version.draft_revision)
