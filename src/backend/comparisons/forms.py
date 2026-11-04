"""Comparison target selection; calculations stay in services."""
from django import forms

from reference.models import ContentVersion
from reference.services import available_content_versions


class TargetChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return (
            f"{obj.title} "
            f"({obj.get_kind_display()}, v{obj.version_no})"
        )


class ComparisonForm(forms.Form):
    target_version = TargetChoiceField(
        queryset=ContentVersion.objects.none(),
        label="Career or job",
        empty_label="Choose a career or job",
        help_text=(
            "The comparison uses your saved, self-reported skill levels."
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["target_version"].queryset = (
            available_content_versions()
            .filter(kind__in=["career", "job"])
            .order_by("title", "-version_no", "pk")
        )