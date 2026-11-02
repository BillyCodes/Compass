"""Private comparisons retain exact inputs and immutable reference editions."""
import uuid

from django.db import models
from django.utils import timezone


class MatchResult(models.Model):
    class MandatoryStatus(models.TextChoices):
        NOT_APPLICABLE = "not_applicable", "Not applicable"
        NOT_MET = "not_met", "Not met"
        UNDETERMINED = "undetermined", "Undetermined"
        MET = "met", "Met"

    match_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey("accounts.Student", on_delete=models.CASCADE, related_name="matches")
    target_version = models.ForeignKey("reference.ContentVersion", on_delete=models.PROTECT, related_name="matches")
    target_kind = models.CharField(max_length=10, choices=[("career", "Career"), ("job", "Job")])
    alg_version = models.CharField(max_length=60)
    score = models.DecimalField(max_digits=5, decimal_places=2)
    mandatory_status = models.CharField(max_length=20, choices=MandatoryStatus.choices)
    reported_count = models.PositiveIntegerField()
    relevant_count = models.PositiveIntegerField()
    is_provisional = models.BooleanField()
    created_at = models.DateTimeField(default=timezone.now)
    # The service assembles children before sealing in one atomic transaction.
    # A deferred database trigger prevents incomplete comparisons from committing.
    finalized = models.BooleanField(default=False, editable=False)
    recommendation_count = models.PositiveIntegerField(default=0, editable=False)

    class Meta:
        db_table = "match_result"
        ordering = ["-created_at", "match_id"]
        constraints = [
            models.UniqueConstraint(fields=["match_id", "target_version"], name="match_target_unique"),
            models.CheckConstraint(condition=models.Q(target_kind__in=["career", "job"]), name="match_kind_allowed"),
            models.CheckConstraint(condition=models.Q(score__gte=0, score__lte=100), name="match_score_0_100"),
            models.CheckConstraint(condition=models.Q(mandatory_status__in=["not_applicable", "not_met", "undetermined", "met"]), name="match_mandatory_allowed"),
            models.CheckConstraint(condition=models.Q(reported_count__gte=1, relevant_count__gte=models.F("reported_count")), name="match_completeness_valid"),
            models.CheckConstraint(condition=(models.Q(is_provisional=True, reported_count__lt=models.F("relevant_count")) | models.Q(is_provisional=False, reported_count=models.F("relevant_count"))), name="match_provisional_consistent"),
            models.CheckConstraint(condition=models.Q(alg_version="weighted_skill_match_v1"), name="match_algorithm_known"),
        ]


class MatchInputSkill(models.Model):
    input_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    match = models.ForeignKey(MatchResult, on_delete=models.CASCADE, related_name="inputs")
    skill = models.ForeignKey("skills.Skill", on_delete=models.PROTECT, related_name="match_inputs")
    # NULL is unreported; an explicit zero is a reported level with no proficiency.
    level_used = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        db_table = "match_input_skill"
        constraints = [
            models.UniqueConstraint(fields=["match", "skill"], name="match_input_unique"),
            models.CheckConstraint(condition=models.Q(level_used__isnull=True) | models.Q(level_used__gte=0, level_used__lte=5), name="match_input_level_0_5"),
        ]


class MatchSkillResult(models.Model):
    class Status(models.TextChoices):
        MET = "met", "Met"
        GAP = "gap", "Gap"
        UNREPORTED = "unreported", "Unreported"

    outcome_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    match = models.ForeignKey(MatchResult, on_delete=models.CASCADE, related_name="outcomes")
    target_version = models.ForeignKey("reference.ContentVersion", on_delete=models.PROTECT, related_name="skill_outcomes")
    skill = models.ForeignKey("skills.Skill", on_delete=models.PROTECT, related_name="match_outcomes")
    status = models.CharField(max_length=10, choices=Status.choices)
    gap = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        db_table = "match_skill_result"
        constraints = [
            models.UniqueConstraint(fields=["match", "skill"], name="match_outcome_unique"),
            models.CheckConstraint(condition=(models.Q(status="unreported", gap__isnull=True) | models.Q(status="met", gap=0, gap__isnull=False) | models.Q(status="gap", gap__gte=1, gap__lte=5, gap__isnull=False)), name="match_outcome_gap_valid"),
        ]


class Recommendation(models.Model):
    recommendation_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    match = models.ForeignKey(MatchResult, on_delete=models.CASCADE, related_name="recommendations")
    resource_version = models.ForeignKey("reference.ContentVersion", on_delete=models.PROTECT, related_name="recommendations")
    resource_kind = models.CharField(max_length=10, choices=[("course", "Course"), ("resource", "Resource")])
    priority_rank = models.PositiveIntegerField()
    # Frozen explanation: skill UUIDs and coverage, not executable or HTML content.
    reason = models.JSONField(default=dict)

    class Meta:
        db_table = "recommendation"
        ordering = ["priority_rank"]
        constraints = [
            models.UniqueConstraint(fields=["match", "resource_version"], name="recommendation_version_unique"),
            models.UniqueConstraint(fields=["match", "priority_rank"], name="recommendation_rank_unique"),
            models.CheckConstraint(condition=models.Q(priority_rank__gte=1), name="recommendation_rank_positive"),
            models.CheckConstraint(condition=models.Q(resource_kind__in=["course", "resource"]), name="recommendation_kind_allowed"),
        ]
