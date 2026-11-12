"""Stable reference identities and numbered editions, shared across content kinds."""
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator, URLValidator
from decimal import Decimal
from django.utils import timezone

from skills.models import ProficiencyLevel
from django.db import models

SOURCE_METADATA_FIELDS = ("provider", "publisher", "author", "source_url", "license_name", "license_url",
                          "attribution_text", "source_version", "external_id", "file_sha256", "raw_metadata")
SOURCE_USAGE_FIELDS = ("usage", "changes", "attribution_note")


class ContentKind(models.TextChoices):
    CAREER = "career", "Career profile"
    JOB = "job", "Job"
    COURSE = "course", "Course"
    RESOURCE = "resource", "Learning resource"
    INSIGHT = "insight", "Professional insight"


class ContentItem(models.Model):
    item_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kind = models.CharField(max_length=10, choices=ContentKind.choices)
    retired_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "content_item"
        constraints = [
            # This redundant candidate key is the target of a typed composite FK.
            models.UniqueConstraint(fields=["item_id", "kind"], name="content_item_id_kind_unique"),
            models.CheckConstraint(
                condition=models.Q(kind__in=["career", "job", "course", "resource", "insight"]),
                name="content_item_kind_allowed",
            ),
        ]


class ContentVersion(models.Model):
    class Origin(models.TextChoices):
        LEGACY = "legacy", "Existing content — origin not reviewed"
        EXTERNAL = "external", "Curated external content"
        ORIGINAL = "original", "Original personal reflection"
        SYNTHETIC = "synthetic", "Synthetic demonstration content"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        RETIRED = "retired", "Retired"

    version_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    item = models.ForeignKey(ContentItem, on_delete=models.PROTECT, related_name="versions")
    kind = models.CharField(max_length=10, choices=ContentKind.choices)
    version_no = models.PositiveIntegerField()
    draft_revision = models.PositiveIntegerField(default=1)
    title = models.CharField(max_length=250)
    body = models.TextField()
    origin = models.CharField(max_length=12, choices=Origin.choices, default=Origin.SYNTHETIC)
    original_author = models.CharField(max_length=150, blank=True)
    originality_confirmed = models.BooleanField(default=False)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_content_versions")
    published_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="published_content_versions")
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "content_version"
        ordering = ["item_id", "version_no"]
        constraints = [
            models.CheckConstraint(condition=models.Q(origin__in=["legacy", "external", "original", "synthetic"]), name="content_origin_allowed"),
            models.CheckConstraint(condition=~models.Q(origin="original") | models.Q(kind="insight"), name="original_content_is_insight"),
            # Do NOT make (item, kind) unique here: an item must support many editions.
            models.UniqueConstraint(fields=["item", "version_no"], name="content_version_number_unique"),
            models.UniqueConstraint(fields=["version_id", "kind"], name="content_version_id_kind_unique"),
            models.CheckConstraint(condition=models.Q(version_no__gte=1), name="content_version_no_positive"),
            models.CheckConstraint(condition=models.Q(draft_revision__gte=1), name="content_draft_revision_positive"),
            models.CheckConstraint(condition=models.Q(kind__in=["career", "job", "course", "resource", "insight"]), name="content_version_kind_allowed"),
            models.CheckConstraint(condition=models.Q(status__in=["draft", "published", "retired"]), name="content_version_status_allowed"),
            models.CheckConstraint(
                condition=(models.Q(published_by__isnull=True, published_at__isnull=True) |
                           models.Q(published_by__isnull=False, published_at__isnull=False)),
                name="content_publication_metadata_paired",
            ),
            models.CheckConstraint(
                condition=(~models.Q(status="published") |
                           models.Q(published_by__isnull=False, published_at__isnull=False)),
                name="content_published_has_attribution",
            ),
        ]

    def clean(self):
        super().clean()
        # Friendly model-level validation; migration 0002 also guards direct SQL.
        if self.item_id:
            kind = ContentItem.objects.filter(pk=self.item_id).values_list("kind", flat=True).first()
            if kind is not None and kind != self.kind:
                raise ValidationError({"kind": "The version kind must match its content item."})

    def __str__(self):
        return f"{self.title} (v{self.version_no})"


class Company(models.Model):
    """Reference organization, not an employer account or authentication identity."""
    company_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company_name = models.CharField(max_length=250)
    industry = models.CharField(max_length=150, blank=True)

    class Meta:
        db_table = "company"
        constraints = [models.CheckConstraint(condition=~models.Q(company_name=""), name="company_name_not_empty")]

    def __str__(self):
        return self.company_name


class ReferenceSource(models.Model):
    """Bibliographic/source information only; no automatic URL fetching."""
    source_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source_title = models.CharField(max_length=250)
    source_url_or_identifier = models.TextField()
    collected_at = models.DateTimeField(default=timezone.now)
    provider = models.CharField(max_length=12, choices=[("unknown", "Not reviewed"), ("onet", "O*NET"),
        ("bls", "BLS"), ("mit", "MIT OpenCourseWare"), ("other", "Other")], default="unknown")
    publisher = models.CharField(max_length=250, blank=True)
    author = models.CharField(max_length=250, blank=True)
    source_url = models.URLField(max_length=2000, blank=True, validators=[URLValidator(schemes=["http", "https"])])
    license_name = models.CharField(max_length=150, blank=True)
    license_url = models.URLField(max_length=2000, blank=True, validators=[URLValidator(schemes=["http", "https"])])
    attribution_text = models.TextField(blank=True)
    source_version = models.CharField(max_length=100, blank=True)
    external_id = models.CharField(max_length=250, blank=True)
    file_sha256 = models.CharField(max_length=64, blank=True, validators=[RegexValidator(r"^[a-f0-9]{64}$", "Use a lowercase SHA-256 digest.")])
    raw_metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "reference_source"
        constraints = [
            models.CheckConstraint(condition=~models.Q(source_title=""), name="source_title_not_empty"),
            models.CheckConstraint(condition=~models.Q(source_url_or_identifier=""), name="source_identifier_not_empty"),
        ]

    def __str__(self):
        return self.source_title

    def clean(self):
        super().clean()
        if not isinstance(self.raw_metadata, dict):
            raise ValidationError({"raw_metadata": "Use a JSON object containing source identifiers and raw values."})


class ContentSource(models.Model):
    class Usage(models.TextChoices):
        UNKNOWN = "unknown", "Not reviewed"
        LINK = "link", "Link only"
        EXCERPT = "excerpt", "Copied excerpt"
        ADAPTED = "adapted", "Adapted content"
        INTERPRETATION = "interpretation", "Compass-authored interpretation"
    source_link_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    version = models.ForeignKey(ContentVersion, on_delete=models.PROTECT, related_name="source_links")
    source = models.ForeignKey(ReferenceSource, on_delete=models.PROTECT, related_name="version_links")
    usage = models.CharField(max_length=16, choices=Usage.choices, default=Usage.UNKNOWN)
    changes = models.TextField(blank=True)
    attribution_note = models.TextField(blank=True)

    class Meta:
        db_table = "content_source"
        constraints = [models.UniqueConstraint(fields=["version", "source"], name="content_source_unique"),
            models.CheckConstraint(condition=models.Q(usage__in=["unknown", "link", "excerpt", "adapted", "interpretation"]), name="source_usage_allowed")]


class VersionKindValidationMixin(models.Model):
    """Friendly validation; migration 0004 independently enforces the typed FK."""

    class Meta:
        abstract = True

    def clean(self):
        super().clean()
        if self.version_id:
            kind = ContentVersion.objects.filter(pk=self.version_id).values_list("kind", flat=True).first()
            if kind is not None and kind != self.kind:
                raise ValidationError({"kind": "The kind must match the referenced version."})


class ContentRequirement(VersionKindValidationMixin):
    requirement_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    version = models.ForeignKey(ContentVersion, on_delete=models.PROTECT, related_name="requirements")
    skill = models.ForeignKey("skills.Skill", on_delete=models.PROTECT, related_name="content_requirements")
    kind = models.CharField(max_length=10, choices=[(ContentKind.CAREER,"Career"),(ContentKind.JOB,"Job")])
    required_level = models.PositiveSmallIntegerField(choices=ProficiencyLevel.choices)
    mandatory = models.BooleanField(default=False)
    weight = models.DecimalField(max_digits=10, decimal_places=4, default=Decimal("1"))

    class Meta:
        db_table = "content_requirement"
        constraints = [
            models.UniqueConstraint(fields=["version", "skill"], name="content_requirement_unique"),
            models.CheckConstraint(condition=models.Q(kind__in=["career", "job"]), name="requirement_kind_allowed"),
            models.CheckConstraint(condition=models.Q(required_level__gte=0, required_level__lte=5), name="requirement_level_0_5"),
            # The finite upper bound also rejects PostgreSQL numeric NaN/Infinity.
            models.CheckConstraint(condition=models.Q(weight__gte=0, weight__lte=Decimal("999999.9999")), name="requirement_weight_finite_nonnegative"),
        ]


class ContentSkill(VersionKindValidationMixin):
    mapping_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    version = models.ForeignKey(ContentVersion, on_delete=models.PROTECT, related_name="skill_mappings")
    skill = models.ForeignKey("skills.Skill", on_delete=models.PROTECT, related_name="learning_mappings")
    kind = models.CharField(max_length=10, choices=[(ContentKind.COURSE,"Course"),(ContentKind.RESOURCE,"Resource")])
    coverage_level = models.PositiveSmallIntegerField(choices=ProficiencyLevel.choices)

    class Meta:
        db_table = "content_skill"
        constraints = [
            models.UniqueConstraint(fields=["version", "skill"], name="content_skill_unique"),
            models.CheckConstraint(condition=models.Q(kind__in=["course", "resource"]), name="content_skill_kind_allowed"),
            models.CheckConstraint(condition=models.Q(coverage_level__gte=0, coverage_level__lte=5), name="coverage_level_0_5"),
        ]


class ContentDetails(VersionKindValidationMixin):
    # One optional detail row per version: no extra surrogate ID is necessary.
    version = models.OneToOneField(ContentVersion, primary_key=True, on_delete=models.PROTECT, related_name="details")
    kind = models.CharField(max_length=10, choices=ContentKind.choices)
    company = models.ForeignKey(Company, on_delete=models.PROTECT, null=True, blank=True, related_name="content_details")
    location = models.CharField(max_length=250, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    course_code = models.CharField(max_length=50, blank=True)
    credits = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    provider = models.CharField(max_length=250, blank=True)
    resource_url = models.URLField(max_length=2000, blank=True, validators=[URLValidator(schemes=["http", "https"])])
    cost_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, blank=True, validators=[RegexValidator(r"^[A-Z]{3}$", "Use three uppercase currency letters.")])

    class Meta:
        db_table = "content_details"
        constraints = [
            models.CheckConstraint(condition=models.Q(kind__in=["career", "job", "course", "resource", "insight"]), name="details_kind_allowed"),
            models.CheckConstraint(condition=(models.Q(kind="job") | models.Q(company__isnull=True, location="", expires_at__isnull=True)), name="details_job_fields_only"),
            models.CheckConstraint(condition=(models.Q(kind="course") | models.Q(course_code="", credits__isnull=True)), name="details_course_fields_only"),
            models.CheckConstraint(condition=(models.Q(kind__in=["course", "resource"]) | models.Q(provider="", resource_url="", cost_amount__isnull=True, currency="")), name="details_learning_fields_only"),
            models.CheckConstraint(condition=(models.Q(credits__isnull=True) | models.Q(credits__gte=0, credits__lte=Decimal("999.99"))), name="details_credits_finite_nonnegative"),
            models.CheckConstraint(condition=(models.Q(cost_amount__isnull=True) | models.Q(cost_amount__gte=0, cost_amount__lte=Decimal("9999999999.99"))), name="details_cost_finite_nonnegative"),
            models.CheckConstraint(condition=(models.Q(cost_amount__isnull=True,currency="") | models.Q(cost_amount__isnull=False,currency__regex=r"^[A-Z]{3}$")), name="details_price_currency_paired"),
        ]


class ContentReview(models.Model):
    """Append-only review of one exact draft revision; edits require a new review."""
    class Decision(models.TextChoices):
        APPROVED = "approved", "Approved"
        CHANGES_REQUESTED = "changes_requested", "Changes requested"

    review_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    version = models.ForeignKey(ContentVersion, on_delete=models.PROTECT, related_name="reviews")
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="content_reviews")
    reviewed_revision = models.PositiveIntegerField()
    decision = models.CharField(max_length=20, choices=Decision.choices)
    reviewed_at = models.DateTimeField(default=timezone.now)
    review_note = models.TextField(blank=True)

    class Meta:
        db_table = "content_review"
        indexes = [models.Index(fields=["version", "reviewed_revision", "-reviewed_at"], name="review_current_revision_idx")]
        constraints = [
            models.CheckConstraint(condition=models.Q(reviewed_revision__gte=1), name="review_revision_positive"),
            models.CheckConstraint(condition=models.Q(decision__in=["approved", "changes_requested"]), name="review_decision_allowed"),
        ]
