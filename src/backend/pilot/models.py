"""Additive tables for the imported Test Launch features.

Nothing here alters an existing table. Student-owned rows (resume imports,
progress snapshots, pasted postings and their saved comparisons) carry a
student foreign key and are only reached through owner-scoped services.
"""
import uuid
from decimal import Decimal

from django.db import models
from django.utils import timezone


class SkillDetail(models.Model):
    """Explorer copy and text-matching aliases for a catalog skill."""
    skill = models.OneToOneField("skills.Skill", primary_key=True, on_delete=models.CASCADE, related_name="detail")
    description = models.CharField(max_length=240, blank=True)
    why_it_matters = models.CharField(max_length=240, blank=True)
    # Comma-separated phrases used to detect the skill in resumes and postings.
    aliases = models.CharField(max_length=400, blank=True)

    class Meta:
        db_table = "skill_detail"

    def alias_list(self):
        names = [self.skill.skill_name] + [a.strip() for a in self.aliases.split(",") if a.strip()]
        return list(dict.fromkeys(n for n in names if n))


class ResumeImport(models.Model):
    """A resume was read. The file is never stored: only its name, size and detected skills."""
    import_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey("accounts.Student", on_delete=models.CASCADE, related_name="resume_imports")
    filename = models.CharField(max_length=120)
    char_count = models.PositiveIntegerField()
    # [{"skill_id": "<uuid>", "name", "category", "hits", "suggested_level", "context"}]
    detected = models.JSONField(default=list)
    applied = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "resume_import"
        ordering = ["-created_at"]


class ProgressSnapshot(models.Model):
    """'Save progress': a dated copy of the student's Skillprint for the Journey view."""
    snapshot_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey("accounts.Student", on_delete=models.CASCADE, related_name="progress_snapshots")
    label = models.CharField(max_length=80, blank=True)
    skills = models.JSONField()       # {skill_uuid: level}
    categories = models.JSONField()   # {category_key: 0-100}
    readiness = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "progress_snapshot"
        ordering = ["-created_at"]


class StudentPosting(models.Model):
    """A job posting a student pasted in. Private to that student."""
    posting_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey("accounts.Student", on_delete=models.CASCADE, related_name="private_postings")
    title = models.CharField(max_length=100)
    company = models.CharField(max_length=80)
    description = models.TextField(max_length=20000)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "student_posting"
        ordering = ["-created_at"]


class StudentPostingRequirement(models.Model):
    requirement_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    posting = models.ForeignKey(StudentPosting, on_delete=models.CASCADE, related_name="requirements")
    skill = models.ForeignKey("skills.Skill", on_delete=models.PROTECT, related_name="private_posting_requirements")
    required_level = models.PositiveSmallIntegerField()
    weight = models.DecimalField(max_digits=10, decimal_places=4, default=Decimal("1"))
    mandatory = models.BooleanField(default=False)

    class Meta:
        db_table = "student_posting_requirement"
        constraints = [
            models.UniqueConstraint(fields=["posting", "skill"], name="student_posting_requirement_unique"),
            models.CheckConstraint(condition=models.Q(required_level__gte=0, required_level__lte=5), name="posting_requirement_level_0_5"),
            models.CheckConstraint(condition=models.Q(weight__gte=0, weight__lte=Decimal("999999.9999")), name="posting_requirement_weight_bounded"),
        ]


class PostingMatch(models.Model):
    """Saved comparison against a private posting; scored by the same versioned algorithm."""
    match_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey("accounts.Student", on_delete=models.CASCADE, related_name="posting_matches")
    posting = models.ForeignKey(StudentPosting, null=True, blank=True, on_delete=models.SET_NULL, related_name="matches")
    target_title = models.CharField(max_length=100)
    target_company = models.CharField(max_length=80)
    alg_version = models.CharField(max_length=60)
    score = models.DecimalField(max_digits=5, decimal_places=2)
    mandatory_status = models.CharField(max_length=20)
    reported_count = models.PositiveIntegerField()
    relevant_count = models.PositiveIntegerField()
    is_provisional = models.BooleanField()
    # Frozen per-skill rows so history never recomputes: skill_id, name, required_level,
    # level_used (null = unreported), weight, mandatory, status, gap.
    detail = models.JSONField()
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "posting_match"
        ordering = ["-created_at", "match_id"]
        constraints = [
            models.CheckConstraint(condition=models.Q(score__gte=0, score__lte=100), name="posting_match_score_0_100"),
            models.CheckConstraint(condition=models.Q(alg_version="weighted_skill_match_v1"), name="posting_match_algorithm_known"),
            models.CheckConstraint(condition=models.Q(mandatory_status__in=["not_applicable", "not_met", "undetermined", "met"]), name="posting_match_mandatory_allowed"),
        ]


class FieldNoteProfile(models.Model):
    """Presentation details for a published `insight` edition (author card, quote, tags)."""
    version = models.OneToOneField("reference.ContentVersion", primary_key=True, on_delete=models.PROTECT, related_name="field_note")
    author_name = models.CharField(max_length=60)
    author_role = models.CharField(max_length=80)
    author_org = models.CharField(max_length=80)
    years_experience = models.PositiveSmallIntegerField(default=5)
    quote = models.CharField(max_length=300)
    working_on = models.TextField()
    learn_next = models.TextField()
    is_sample = models.BooleanField(default=True)
    skills = models.ManyToManyField("skills.Skill", related_name="field_notes", blank=True)

    class Meta:
        db_table = "field_note_profile"

    @property
    def initials(self):
        return "".join(p[0] for p in self.author_name.split()[:2]).upper()
