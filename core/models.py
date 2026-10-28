"""
COMPASS Test Launch 01 — data model.

Follows Engineering Blueprint §6:
  * ACCOUNT (identity, credential, status) is separate from STUDENT (academic profile).
  * STUDENT carries an opaque student_id used by every student-owned table.
  * Reference content (skills, courses, career profiles, sample postings, field notes)
    is separate from private student data.
  * Saved comparison results keep the target version, algorithm version and the
    minimal input snapshot needed to explain them later.
"""
import uuid

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

# ---------------------------------------------------------------------------
# Skill scale (TEAM DECISION GATE — "Skill scale" is OPEN in the decision
# register). This pilot uses a 1–5 ordinal scale. Change it here and in
# services/comparison.py together, then bump ALGORITHM_VERSION.
# ---------------------------------------------------------------------------
SKILL_LEVELS = [
    (1, "Aware"),
    (2, "Beginner"),
    (3, "Developing"),
    (4, "Proficient"),
    (5, "Advanced"),
]
LEVEL_LABELS = dict(SKILL_LEVELS)
level_validators = [MinValueValidator(1), MaxValueValidator(5)]


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------
class AccountManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra):
        if not email:
            raise ValueError("Email is required")
        email = self.normalize_email(email).lower()
        account = self.model(email=email, **extra)
        account.set_password(password)  # PBKDF2 via Django's maintained hasher
        account.save(using=self._db)
        return account

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("role", Account.Role.ADMIN)
        return self.create_user(email, password, **extra)


class Account(AbstractBaseUser, PermissionsMixin):
    """Authentication identity and account state. Holds no academic data."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        DISABLED = "disabled", "Disabled"
        REVOKED = "revoked", "Revoked"

    class Role(models.TextChoices):
        STUDENT = "student", "Student"
        MAINTAINER = "maintainer", "Content Maintainer"
        ADMIN = "admin", "Administrator"

    account_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    email = models.EmailField(unique=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE)
    role = models.CharField(max_length=12, choices=Role.choices, default=Role.STUDENT)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    objects = AccountManager()
    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = []

    # Django's auth backend refuses users whose is_active is False, so account
    # status drives login and session continuation from one place.
    @property
    def is_active(self):
        return self.status == self.Status.ACTIVE

    @is_active.setter
    def is_active(self, value):
        self.status = self.Status.ACTIVE if value else self.Status.DISABLED

    def is_account_active(self):
        return self.status == self.Status.ACTIVE

    def __str__(self):
        return self.email


class Student(models.Model):
    """Academic/career profile. One account → zero or one student profile."""

    student_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="student")
    name = models.CharField(max_length=80)
    major = models.CharField(max_length=80, blank=True)
    career_interests = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    # The only profile fields a student may write (blueprint §5.3 field allowlist).
    EDITABLE_FIELDS = ("name", "major", "career_interests")

    @property
    def first_name(self):
        return (self.name or "").split(" ")[0]

    def __str__(self):
        return self.name


# ---------------------------------------------------------------------------
# Reference catalog
# ---------------------------------------------------------------------------
class SkillCategory(models.TextChoices):
    PROGRAMMING = "programming", "Programming"
    DATA = "data", "Data"
    SYSTEMS = "systems", "Systems"
    CLOUD = "cloud", "Cloud / Tools"
    SECURITY = "security", "Cybersecurity"
    PROFESSIONAL = "professional", "Communication"


class Skill(models.Model):
    skill_id = models.SlugField(primary_key=True, max_length=40)
    name = models.CharField(max_length=60, unique=True)
    category = models.CharField(max_length=16, choices=SkillCategory.choices)
    description = models.CharField(max_length=240, blank=True)
    why_it_matters = models.CharField(max_length=240, blank=True)
    # Comma-separated phrases used to detect the skill in resumes and postings.
    aliases = models.CharField(max_length=400, blank=True)

    class Meta:
        ordering = ["category", "name"]

    def alias_list(self):
        names = [self.name] + [a.strip() for a in self.aliases.split(",") if a.strip()]
        return list(dict.fromkeys(n for n in names if n))

    def __str__(self):
        return self.name


class UniversityCourse(models.Model):
    course_id = models.SlugField(primary_key=True, max_length=20)
    course_code = models.CharField(max_length=12, unique=True)
    course_name = models.CharField(max_length=100)
    skills = models.ManyToManyField(Skill, through="CourseSkill", related_name="courses")

    class Meta:
        ordering = ["course_code"]

    def __str__(self):
        return f"{self.course_code} {self.course_name}"


class CourseSkill(models.Model):
    course = models.ForeignKey(UniversityCourse, on_delete=models.CASCADE)
    skill = models.ForeignKey(Skill, on_delete=models.CASCADE)
    coverage_level = models.PositiveSmallIntegerField(validators=level_validators, default=2)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["course", "skill"], name="uniq_course_skill")]


# ---------------------------------------------------------------------------
# Student-owned data
# ---------------------------------------------------------------------------
class StudentSkill(models.Model):
    class Source(models.TextChoices):
        SELF = "self", "Self-reported"
        RESUME = "resume", "From resume"
        COURSE = "course", "From coursework"

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="skills")
    skill = models.ForeignKey(Skill, on_delete=models.PROTECT)
    level = models.PositiveSmallIntegerField(validators=level_validators)
    evidence = models.CharField(max_length=240, blank=True)
    source = models.CharField(max_length=8, choices=Source.choices, default=Source.SELF)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["student", "skill"], name="uniq_student_skill"),
            models.CheckConstraint(condition=models.Q(level__gte=1, level__lte=5), name="student_skill_level_1_5"),
        ]
        ordering = ["-level", "skill__name"]

    @property
    def level_label(self):
        return LEVEL_LABELS.get(self.level, "")


class StudentCourse(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="courses")
    course = models.ForeignKey(UniversityCourse, on_delete=models.PROTECT)
    term = models.CharField(max_length=20, blank=True)
    added_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["student", "course"], name="uniq_student_course")]


class ResumeImport(models.Model):
    """Record that a resume was read. The file itself is never stored (data minimization);
    only the filename, size and the skills detected in it."""

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="resume_imports")
    filename = models.CharField(max_length=120)
    char_count = models.PositiveIntegerField()
    detected = models.JSONField(default=list)   # [{"skill_id", "name", "suggested_level", "hits", "context"}]
    applied = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]


# ---------------------------------------------------------------------------
# Comparison targets (versioned reference content)
# ---------------------------------------------------------------------------
class CareerProfile(models.Model):
    """A reviewed, versioned career destination. A new version is a new row;
    published rows are never edited in place once results reference them."""

    slug = models.SlugField(max_length=60)
    version = models.PositiveSmallIntegerField(default=1)
    title = models.CharField(max_length=80)
    summary = models.CharField(max_length=300)
    is_published = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["slug", "version"], name="uniq_career_version")]
        ordering = ["title", "-version"]

    def __str__(self):
        return f"{self.title} (v{self.version})"


class CareerRequirement(models.Model):
    profile = models.ForeignKey(CareerProfile, on_delete=models.CASCADE, related_name="requirements")
    skill = models.ForeignKey(Skill, on_delete=models.PROTECT)
    required_level = models.PositiveSmallIntegerField(validators=level_validators)
    weight = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1), MaxValueValidator(5)])
    mandatory = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["profile", "skill"], name="uniq_career_req")]


class JobPosting(models.Model):
    """A job posting to compare against.

    owner = NULL → a pilot sample posting visible to every student (fictional company).
    owner = a student → a posting that student pasted in; private to them.
    Requirements are stored as parsed rows so the comparison is reproducible.
    """

    owner = models.ForeignKey(Student, null=True, blank=True, on_delete=models.CASCADE, related_name="postings")
    title = models.CharField(max_length=100)
    company = models.CharField(max_length=80)
    location = models.CharField(max_length=80, blank=True)
    tags = models.CharField(max_length=120, blank=True)
    description = models.TextField(max_length=20000, blank=True)
    version = models.PositiveSmallIntegerField(default=1)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]

    @property
    def is_sample(self):
        return self.owner_id is None

    def tag_list(self):
        return [t.strip() for t in self.tags.split(",") if t.strip()]

    def __str__(self):
        return f"{self.title} — {self.company}"


class PostingRequirement(models.Model):
    posting = models.ForeignKey(JobPosting, on_delete=models.CASCADE, related_name="requirements")
    skill = models.ForeignKey(Skill, on_delete=models.PROTECT)
    required_level = models.PositiveSmallIntegerField(validators=level_validators, default=3)
    weight = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1), MaxValueValidator(5)])
    mandatory = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["posting", "skill"], name="uniq_posting_req")]


class MatchResult(models.Model):
    """A saved comparison. Owned by one student; values computed only on the server."""

    class TargetType(models.TextChoices):
        CAREER = "career", "Career profile"
        POSTING = "posting", "Job posting"

    result_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="results")
    target_type = models.CharField(max_length=8, choices=TargetType.choices)
    career_profile = models.ForeignKey(CareerProfile, null=True, blank=True, on_delete=models.PROTECT)
    posting = models.ForeignKey(JobPosting, null=True, blank=True, on_delete=models.SET_NULL)
    target_title = models.CharField(max_length=180)
    target_version = models.PositiveSmallIntegerField()
    algorithm_version = models.CharField(max_length=20)
    score = models.DecimalField(max_digits=5, decimal_places=1)
    status = models.CharField(max_length=24)
    mandatory_met = models.PositiveSmallIntegerField()
    mandatory_total = models.PositiveSmallIntegerField()
    requirements_met = models.PositiveSmallIntegerField()
    requirements_total = models.PositiveSmallIntegerField()
    detail = models.JSONField()          # per-skill outcomes
    input_snapshot = models.JSONField()  # {"skills": {skill_id: level}, "requirements": [...]}
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(condition=models.Q(score__gte=0, score__lte=100), name="match_score_0_100"),
        ]


class ProgressSnapshot(models.Model):
    """'Save progress': a dated copy of the student's Skillprint for the Journey view."""

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="snapshots")
    label = models.CharField(max_length=80, blank=True)
    skills = models.JSONField()       # {skill_id: level}
    categories = models.JSONField()   # {category: 0-100}
    readiness = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]


# ---------------------------------------------------------------------------
# Field Notes (pilot: sample content written by the team, fictional authors)
# ---------------------------------------------------------------------------
class FieldNote(models.Model):
    author_name = models.CharField(max_length=60)
    author_role = models.CharField(max_length=80)
    author_org = models.CharField(max_length=80)
    years_experience = models.PositiveSmallIntegerField(default=5)
    headline = models.CharField(max_length=160)
    quote = models.CharField(max_length=300)
    body = models.TextField()
    working_on = models.TextField(help_text="What the professional's team is working on right now")
    learn_next = models.TextField(help_text="What they recommend students learn")
    skills = models.ManyToManyField(Skill, related_name="field_notes", blank=True)
    is_sample = models.BooleanField(default=True)
    published_at = models.DateField(default=timezone.localdate)

    class Meta:
        ordering = ["-published_at", "author_name"]

    @property
    def initials(self):
        return "".join(p[0] for p in self.author_name.split()[:2]).upper()

    def __str__(self):
        return f"{self.author_name}: {self.headline}"
