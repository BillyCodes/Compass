from django import forms

from .models import Company, ContentKind

from skills.models import ProficiencyLevel, Skill

class CreateContentForm(forms.Form):
    kind = forms.ChoiceField(
        label="Content type",
        choices=ContentKind.choices,
        widget=forms.Select(attrs={"class": "input"}),
    )

    title = forms.CharField(
        label="Title",
        max_length=250,
        widget=forms.TextInput(attrs={"class": "input"}),
    )

    body = forms.CharField(
        label="Description",
        widget=forms.Textarea(
            attrs={"class": "input", "rows": 8}
        ),
    )


class EditContentForm(forms.Form):
    title = forms.CharField(
        label="Title",
        max_length=250,
        widget=forms.TextInput(attrs={"class": "input"}),
    )

    body = forms.CharField(
        label="Description",
        widget=forms.Textarea(
            attrs={"class": "input", "rows": 8}
        ),
    )

    expected_revision = forms.IntegerField(
        min_value=1,
        widget=forms.HiddenInput(),
    )


class AddSourceForm(forms.Form):
    source_title = forms.CharField(
        label="Source title",
        max_length=250,
        widget=forms.TextInput(
            attrs={
                "class": "input",
                "placeholder": "Title of the source",
            }
        ),
    )

    source_url_or_identifier = forms.CharField(
        label="Source URL or identifier",
        help_text=(
            "Enter a source URL or a reference identifier. "
            "Clearly label synthetic test sources."
        ),
        widget=forms.Textarea(
            attrs={
                "class": "input",
                "rows": 3,
                "placeholder": "URL or reference identifier",
            }
        ),
    )

    expected_revision = forms.IntegerField(
        min_value=1,
        widget=forms.HiddenInput(),
    )

class EditSourceForm(AddSourceForm):
    """Use the same source fields when correcting a draft's reference."""
    pass

class ContentRequirementForm(forms.Form):
    skill = forms.ModelChoiceField(
        label="Skill",
        queryset=Skill.objects.none(),
        empty_label="Select a skill",
        widget=forms.Select(attrs={"class": "input"}),
    )

    required_level = forms.TypedChoiceField(
        label="Required proficiency level",
        choices=ProficiencyLevel.choices,
        coerce=int,
        widget=forms.Select(attrs={"class": "input"}),
    )

    mandatory = forms.BooleanField(
        label="Mandatory requirement",
        required=False,
        help_text="Select if this skill is a mandatory requirement.",
        widget=forms.CheckboxInput(),
    )

    weight = forms.DecimalField(
        label="Weight",
        min_value=0,
        max_digits=10,
        decimal_places=4,
        initial=1,
        help_text=(
            "Relative importance of this skill. "
            "For example, weight 2 gives twice the weight of 1. "
            "A weight of 0 does not contribute to the weighted score."
        ),
        widget=forms.NumberInput(
            attrs={
                "class": "input",
                "min": "0",
                "max": "999999.9999",
                "step": "0.0001",
            }
        ),
    )

    expected_revision = forms.IntegerField(
        min_value=1,
        widget=forms.HiddenInput(),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["skill"].queryset = (
            Skill.objects
            .filter(status=Skill.Status.ACTIVE)
            .order_by("skill_name")
        )

class JobDetailsForm(forms.Form):
    company = forms.ModelChoiceField(
        label="Company",
        queryset=Company.objects.none(),
        required=False,
        empty_label="No company selected",
        widget=forms.Select(attrs={"class": "input"}),
    )

    location = forms.CharField(
        label="Location",
        max_length=250,
        required=False,
        help_text="For example: Canton, Mississippi, or Remote.",
        widget=forms.TextInput(
            attrs={
                "class": "input",
                "placeholder": "City, region, or Remote",
            }
        ),
    )

    expires_at = forms.DateTimeField(
        label="Expiration date and time",
        required=False,
        input_formats=[
            "%Y-%m-%dT%H:%M",
            "%Y-%m-%dT%H:%M:%S",
        ],
        help_text=(
            "Optional. Use the application's current time zone. "
            "Expired content cannot be published."
        ),
        widget=forms.DateTimeInput(
            format="%Y-%m-%dT%H:%M",
            attrs={
                "class": "input",
                "type": "datetime-local",
                "step": "60",
            },
        ),
    )

    expected_revision = forms.IntegerField(
        min_value=1,
        widget=forms.HiddenInput(),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["company"].queryset = (
            Company.objects.order_by("company_name")
        )

class CompanyForm(forms.Form):
    company_name = forms.CharField(
        label="Company name",
        max_length=250,
        widget=forms.TextInput(attrs={"class": "input"}),
    )

    industry = forms.CharField(
        label="Industry",
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={"class": "input"}),
    )