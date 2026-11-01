"""Stable reference identities and numbered editions, shared across content kinds."""
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


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
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_content_versions")
    published_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="published_content_versions")
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "content_version"
        ordering = ["item_id", "version_no"]
        constraints = [
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
