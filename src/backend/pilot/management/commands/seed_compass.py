"""Load synthetic Test Launch sample content through the approved review/publish services.

    python manage.py seed_compass                       # reference content only (idempotent)
    python manage.py seed_compass --demo-student EMAIL  # also give an EXISTING student account sample skills

Reference content is authored and published by a synthetic maintainer through the
normal publication service. That account has an unusable password. Create sign-in
accounts separately with `create_demo_accounts`.
"""
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import Account, AccountRole, Role, Student
from auditing.models import AuditEvent
from auditing.services import _record_event
from comparisons.services import create_comparison
from pilot import seed_data
from pilot.models import FieldNoteProfile, ProgressSnapshot, SkillDetail
from pilot.services.skillprint import CATEGORY_LABELS, category_scores
from reference import services as ref
from reference.models import Company, ContentItem, ContentVersion, ReferenceSource
from skills.models import Skill
from skills.services import select_student_course, set_student_skill

AUTHOR_EMAIL = "seed.author@example.test"
SOURCE_TITLE = "Compass Test Launch sample data (synthetic)"


class Command(BaseCommand):
    help = "Load synthetic skills, courses, careers, jobs and field notes via the approved services."

    def add_arguments(self, parser):
        parser.add_argument("--demo-student", metavar="EMAIL", help="Give an existing student account sample skills, courses, saved progress and one comparison.")

    def handle(self, *args, **options):
        demo = options.get("demo_student")
        student = None
        if demo:
            student = Student.objects.filter(account__login_email__iexact=demo.strip()).first()
            if student is None:
                raise CommandError("No student account with that email. Create one first (create_demo_accounts or register).")
        self.author = self._maintainer(AUTHOR_EMAIL)
        self.source = ReferenceSource.objects.get_or_create(
            source_title=SOURCE_TITLE, defaults={"source_url_or_identifier": "synthetic-pilot-content"})[0]
        self.skills = self._skills()
        created = {"course": 0, "career": 0, "job": 0, "insight": 0}
        for _cid, code, name, covers in seed_data.COURSES:
            created["course"] += self._publish(
                kind="course", title=f"{code} {name}", body=f"{name} at the university, as listed in the pilot course catalog.",
                details={"course_code": code}, mappings=[(self.skills[s], lvl) for s, lvl in covers])
        for slug, title, summary, reqs in seed_data.CAREERS:
            created["career"] += self._publish(kind="career", title=title, body=summary, requirements=self._reqs(reqs))
        for p in seed_data.POSTINGS:
            company = Company.objects.get_or_create(company_name=p["company"], defaults={"industry": p["tags"].split(",")[0]})[0]
            created["job"] += self._publish(kind="job", title=p["title"], body=p["description"], requirements=self._reqs(p["reqs"]),
                                            details={"company_id": company.pk, "location": p["location"]})
        for n in seed_data.FIELD_NOTES:
            created["insight"] += self._publish(kind="insight", title=n["headline"], body=n["body"], note=n)
        if student is not None:
            self._demo_student(student)
        self.stdout.write(self.style.SUCCESS(
            f"Skills: {len(self.skills)}. New published editions: {created}. Existing content was left unchanged."))

    # -- accounts -------------------------------------------------------------
    @transaction.atomic
    def _maintainer(self, email):
        account = Account.objects.filter(login_email=email).first()
        if account is None:
            account = Account.objects.create_user(email, None)  # unusable password: cannot sign in
            AccountRole.objects.create(account=account, role=Role.objects.get(role_name="maintainer"))
            _record_event(event_type=AuditEvent.Type.ROLE_ASSIGNED, subject=account, metadata={"role_name": "maintainer"})
        return account

    # -- catalog ----------------------------------------------------------------
    @transaction.atomic
    def _skills(self):
        out = {}
        for sid, name, key, aliases, description, why in seed_data.SKILLS:
            skill, _ = Skill.objects.get_or_create(skill_name=name, defaults={"category": CATEGORY_LABELS[key]})
            SkillDetail.objects.update_or_create(skill=skill, defaults={"description": description, "why_it_matters": why, "aliases": aliases})
            out[sid] = skill
        return out

    def _reqs(self, rows):
        return [(self.skills[s], lvl, Decimal(w), bool(m)) for s, lvl, w, m in rows]

    def _publish(self, *, kind, title, body, requirements=(), mappings=(), details=None, note=None):
        if ContentVersion.objects.filter(kind=kind, title=title).exists():
            return 0
        with transaction.atomic():
            item = ref.create_content_item(actor=self.author, kind=kind)
            version = ref.create_draft_version(actor=self.author, item_id=item.pk, title=title, body=body)
            rev = lambda: ContentVersion.objects.get(pk=version.pk).draft_revision  # noqa: E731
            for skill, level, weight, mandatory in requirements:
                ref.set_requirement(actor=self.author, version_id=version.pk, skill_id=skill.pk, required_level=level,
                                    mandatory=mandatory, weight=weight, expected_revision=rev())
            for skill, level in mappings:
                ref.set_skill_mapping(actor=self.author, version_id=version.pk, skill_id=skill.pk, coverage_level=level, expected_revision=rev())
            if details:
                ref.set_content_details(actor=self.author, version_id=version.pk, expected_revision=rev(), **details)
            ref.attach_source(actor=self.author, version_id=version.pk, source_id=self.source.pk, expected_revision=rev())
            if note:
                profile = FieldNoteProfile.objects.create(
                    version_id=version.pk, author_name=note["author_name"], author_role=note["author_role"], author_org=note["author_org"],
                    years_experience=note["years"], quote=note["quote"], working_on=note["working_on"], learn_next=note["learn_next"], is_sample=True)
                profile.skills.set([self.skills[s] for s in note["skills"]])
            ref.publish_content_version(actor=self.author, version_id=version.pk, expected_revision=rev())
        return 1

    # -- optional demo student -------------------------------------------------
    @transaction.atomic
    def _demo_student(self, student):
        actor, now = student.account, timezone.now()
        for sid, level, evidence in seed_data.STUDENT_A_SKILLS:
            set_student_skill(actor=actor, skill_id=self.skills[sid].pk, proficiency_level=level, evidence_text=evidence)
        for code in ("CSC 228", "CSC 312", "CSC 435", "CSC 450"):
            version = ContentVersion.objects.filter(kind="course", title__startswith=code, status="published").first()
            if version is not None:
                try:
                    select_student_course(actor=actor, course_item_id=version.item_id)
                except ValidationError:
                    pass
        if not ProgressSnapshot.objects.filter(student=student).exists():
            for days, label, levels in seed_data.STUDENT_A_HISTORY:
                buckets = {}
                for sid, level in levels.items():
                    key = next(k for s, _, k, *_ in seed_data.SKILLS if s == sid)
                    buckets.setdefault(key, []).append(level)
                ProgressSnapshot.objects.create(student=student, label=label, skills={str(self.skills[s].pk): v for s, v in levels.items()},
                                                categories=category_scores(buckets), created_at=now - timedelta(days=days))
        cloud = ContentVersion.objects.filter(kind="career", title="Cloud Engineer", status="published").first()
        if cloud is not None:
            create_comparison(actor=actor, target_version_id=cloud.pk)
