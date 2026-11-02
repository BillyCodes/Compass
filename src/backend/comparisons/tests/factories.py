"""Synthetic users and fully reviewed content for comparison tests."""
from accounts.models import Account, AccountRole, Role
from accounts.services import create_student
from reference.models import ContentRequirement
from reference.services import (create_content_item, create_draft_version, publish_content_version,
                                review_content_version, set_requirement, set_skill_mapping)
from reference.tests.factories import prepare_for_publication
from skills.models import Skill


def setup_actors(test):
    for name in ("student","maintainer","administrator"):
        Role.objects.get_or_create(role_name=name)
    test.student = create_student(email="compare.a@example.test",password=None,display_name="Comparison A")
    test.other = create_student(email="compare.b@example.test",password=None,display_name="Comparison B")
    test.author = Account.objects.create_user("compare.author@example.test")
    test.reviewer = Account.objects.create_user("compare.reviewer@example.test")
    for actor in (test.author,test.reviewer):
        AccountRole.objects.create(account=actor,role=Role.objects.get(role_name="maintainer"))
    test.python = Skill.objects.create(skill_name="Python")
    test.sql = Skill.objects.create(skill_name="SQL")


def draft(test,kind="career",item=None):
    item = item or create_content_item(actor=test.author,kind=kind)
    version = create_draft_version(actor=test.author,item_id=item.pk,title="Synthetic comparison target",body="Synthetic reference body")
    prepare_for_publication(version,test.author)
    return version


def approve(test,version):
    version.refresh_from_db()
    review_content_version(actor=test.reviewer,version_id=version.pk,expected_revision=version.draft_revision,decision="approved")
    return publish_content_version(actor=test.author,version_id=version.pk,expected_revision=version.draft_revision)


def target(test,kind="career",requirements=None):
    version = draft(test,kind)
    # Replace the helper's generic fixture requirement before publication.
    ContentRequirement.objects.filter(version=version).delete()
    for skill,level,weight,mandatory in requirements or [(test.python,4,"2",True),(test.sql,3,"1",False)]:
        version.refresh_from_db()
        set_requirement(actor=test.author,version_id=version.pk,expected_revision=version.draft_revision,
                        skill_id=skill.pk,required_level=level,weight=weight,mandatory=mandatory)
    return approve(test,version)


def learning(test,skill,coverage=4,kind="course",item=None):
    version = draft(test,kind,item)
    version.refresh_from_db()
    set_skill_mapping(actor=test.author,version_id=version.pk,expected_revision=version.draft_revision,
                      skill_id=skill.pk,coverage_level=coverage)
    return approve(test,version)
