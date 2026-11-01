"""Skill vocabulary and private, self-reported student proficiency."""
import uuid

from django.db import models


class ProficiencyLevel(models.IntegerChoices):
    NONE = 0, "None"
    AWARENESS = 1, "Awareness"
    BEGINNER = 2, "Beginner"
    INTERMEDIATE = 3, "Intermediate"
    ADVANCED = 4, "Advanced"
    EXPERT = 5, "Expert"


class Skill(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        RETIRED = "retired", "Retired"

    skill_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    skill_name = models.CharField(max_length=150, unique=True)
    category = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)

    class Meta:
        db_table = "skill"
        ordering = ["skill_name"]
        constraints = [
            models.CheckConstraint(condition=models.Q(status__in=["active", "retired"]), name="skill_status_allowed"),
            models.CheckConstraint(condition=~models.Q(skill_name=""), name="skill_name_not_empty"),
        ]

    def __str__(self):
        return self.skill_name


class StudentSkill(models.Model):
    # The UUID is a Django-friendly physical key; the logical pair remains unique.
    student_skill_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey("accounts.Student", on_delete=models.CASCADE, related_name="skill_records")
    skill = models.ForeignKey(Skill, on_delete=models.PROTECT, related_name="student_records")
    proficiency_level = models.PositiveSmallIntegerField(choices=ProficiencyLevel.choices)
    evidence_text = models.TextField(blank=True)  # Plain text, not verified evidence.
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "student_skill"
        constraints = [
            models.UniqueConstraint(fields=["student", "skill"], name="student_skill_unique"),
            models.CheckConstraint(
                condition=models.Q(proficiency_level__gte=0, proficiency_level__lte=5),
                name="student_skill_level_0_5",
            ),
        ]
