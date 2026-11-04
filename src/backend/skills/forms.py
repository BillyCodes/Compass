"""Student proficiency input; persistence stays in skills.services."""
from django import forms

from .models import ProficiencyLevel, Skill

from django.db.models import OuterRef, Subquery

from reference.models import ContentItem, ContentKind, ContentVersion

class StudentSkillForm(forms.Form):
    skill = forms.ModelChoiceField(
        queryset=Skill.objects.none(),
        label="Skill",
        empty_label="Choose a skill",
    )
    proficiency_level = forms.TypedChoiceField(
        choices=ProficiencyLevel.choices,
        coerce=int,
        label="Proficiency level",
    )
    evidence_text = forms.CharField(
        required=False,
        label="Supporting description",
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "placeholder": "Describe your experience with this skill.",
            }
        ),
        help_text="Self-reported information; do not include sensitive data.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["skill"].queryset = Skill.objects.filter(
            status=Skill.Status.ACTIVE,
        ).order_by("skill_name")

class CourseChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f"{obj.selection_title} — v{obj.selection_version_no}"


class StudentCourseForm(forms.Form):
    course_item = CourseChoiceField(
        queryset=ContentItem.objects.none(),
        label="Course",
        empty_label="Choose a course",
        help_text=(
            "Selecting a course does not record enrollment, "
            "completion, or verified proficiency."
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        published_versions = ContentVersion.objects.filter(
            item_id=OuterRef("pk"),
            kind=ContentKind.COURSE,
            status=ContentVersion.Status.PUBLISHED,
        ).order_by("-version_no")

        self.fields["course_item"].queryset = (
            ContentItem.objects.filter(
                kind=ContentKind.COURSE,
                retired_at__isnull=True,
            )
            .annotate(
                selection_title=Subquery(
                    published_versions.values("title")[:1]
                ),
                selection_version_no=Subquery(
                    published_versions.values("version_no")[:1]
                ),
            )
            .filter(selection_version_no__isnull=False)
            .order_by("selection_title", "item_id")
        )