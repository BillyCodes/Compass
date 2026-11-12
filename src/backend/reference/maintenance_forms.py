from django import forms

from django.core.validators import URLValidator

from .models import Company, ContentKind, ContentVersion, ReferenceSource, ContentSource, SOURCE_METADATA_FIELDS, SOURCE_USAGE_FIELDS

from skills.models import ProficiencyLevel, Skill

class ContentOriginForm(forms.Form):
    origin = forms.ChoiceField(choices=ContentVersion.Origin.choices,
        initial=ContentVersion.Origin.EXTERNAL, required=False,
        help_text="Classify the draft before publication. Synthetic means demonstration data, not sourced real-world content.")
    original_author = forms.CharField(max_length=150, required=False, label="Original reflection author",
        help_text="Required for an original personal reflection; use an accurate author name.")
    originality_confirmed = forms.BooleanField(required=False,
        label="I confirm this is original personal reflection and all borrowed material is appropriately cited.")


class SourceProvenanceForm(forms.Form):
    provider = ReferenceSource._meta.get_field("provider").formfield(required=False)
    publisher = ReferenceSource._meta.get_field("publisher").formfield(required=False)
    author = ReferenceSource._meta.get_field("author").formfield(required=False)
    source_url = ReferenceSource._meta.get_field("source_url").formfield(required=False)
    license_name = ReferenceSource._meta.get_field("license_name").formfield(required=False)
    license_url = ReferenceSource._meta.get_field("license_url").formfield(required=False)
    attribution_text = ReferenceSource._meta.get_field("attribution_text").formfield(required=False)
    source_version = ReferenceSource._meta.get_field("source_version").formfield(required=False)
    external_id = ReferenceSource._meta.get_field("external_id").formfield(required=False)
    file_sha256 = ReferenceSource._meta.get_field("file_sha256").formfield(required=False)
    raw_metadata = ReferenceSource._meta.get_field("raw_metadata").formfield(required=False)
    usage = ContentSource._meta.get_field("usage").formfield(required=False)
    changes = ContentSource._meta.get_field("changes").formfield(required=False)
    attribution_note = ContentSource._meta.get_field("attribution_note").formfield(required=False)

    def source_metadata(self):
        values = {field: self.cleaned_data[field] for field in SOURCE_METADATA_FIELDS}
        values["provider"] = values["provider"] or "unknown"
        values["raw_metadata"] = values["raw_metadata"] or {}
        return values

    def source_usage(self):
        values = {field: self.cleaned_data[field] for field in SOURCE_USAGE_FIELDS}
        values["usage"] = values["usage"] or "unknown"
        return values


class CreateContentForm(ContentOriginForm):
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


class EditContentForm(ContentOriginForm):
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


class AddSourceForm(SourceProvenanceForm):
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

class CourseDetailsForm(forms.Form):
    course_code = forms.CharField(
        label="Course code",
        max_length=50,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "input",
                "placeholder": "For example: CS101",
            }
        ),
    )

    credits = forms.DecimalField(
        label="Credits",
        required=False,
        min_value=0,
        max_digits=5,
        decimal_places=2,
        widget=forms.NumberInput(
            attrs={
                "class": "input",
                "min": "0",
                "max": "999.99",
                "step": "0.01",
            }
        ),
    )

    provider = forms.CharField(
        label="Institution or provider",
        max_length=250,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "input",
                "placeholder": "University, college, or course provider",
            }
        ),
    )

    resource_url = forms.URLField(
        label="Course URL",
        max_length=2000,
        required=False,
        validators=[
            URLValidator(schemes=["http", "https"]),
        ],
        widget=forms.URLInput(
            attrs={
                "class": "input",
                "placeholder": "https://example.com/course",
            }
        ),
    )

    cost_amount = forms.DecimalField(
        label="Cost",
        required=False,
        min_value=0,
        max_digits=12,
        decimal_places=2,
        help_text=(
            "Leave blank if unknown. "
            "Enter 0 if the course is free."
        ),
        widget=forms.NumberInput(
            attrs={
                "class": "input",
                "min": "0",
                "max": "9999999999.99",
                "step": "0.01",
            }
        ),
    )

    currency = forms.CharField(
        label="Currency",
        max_length=3,
        required=False,
        help_text="Three letters, for example USD.",
        widget=forms.TextInput(
            attrs={
                "class": "input",
                "placeholder": "USD",
                "maxlength": "3",
            }
        ),
    )

    expected_revision = forms.IntegerField(
        min_value=1,
        widget=forms.HiddenInput(),
    )

    def clean_currency(self):
        currency = self.cleaned_data["currency"].upper()

        if currency and (
            len(currency) != 3
            or not all("A" <= character <= "Z" for character in currency)
        ):
            raise forms.ValidationError(
                "Use three currency letters, for example USD."
            )

        return currency

    def clean(self):
        cleaned_data = super().clean()

        cost_amount = cleaned_data.get("cost_amount")
        currency = cleaned_data.get("currency")

        if (
            "cost_amount" in self.errors
            or "currency" in self.errors
        ):
            return cleaned_data

        if cost_amount is not None and not currency:
            self.add_error(
                "currency",
                "Enter a currency when a cost is provided.",
            )

        if currency and cost_amount is None:
            self.add_error(
                "cost_amount",
                "Enter a cost when a currency is provided.",
            )

        return cleaned_data

class ContentSkillForm(forms.Form):
    skill = forms.ModelChoiceField(
        label="Skill",
        queryset=Skill.objects.none(),
        empty_label="Select a skill",
        widget=forms.Select(
            attrs={"class": "input"}
        ),
    )

    coverage_level = forms.TypedChoiceField(
        label="Skill coverage level",
        choices=ProficiencyLevel.choices,
        coerce=int,
        help_text=(
            "Select the proficiency level this learning content "
            "is intended to cover."
        ),
        widget=forms.Select(
            attrs={"class": "input"}
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


class RemoveSkillMappingForm(forms.Form):
    expected_revision = forms.IntegerField(
        min_value=1,
        widget=forms.HiddenInput(),
    )  

class ResourceDetailsForm(forms.Form):
    provider = forms.CharField(
        label="Provider",
        max_length=250,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "input",
                "placeholder": "Organization or resource provider",
            }
        ),
    )

    resource_url = forms.URLField(
        label="Resource URL",
        max_length=2000,
        required=False,
        validators=[
            URLValidator(schemes=["http", "https"]),
        ],
        widget=forms.URLInput(
            attrs={
                "class": "input",
                "placeholder": "https://example.com/resource",
            }
        ),
    )

    cost_amount = forms.DecimalField(
        label="Cost",
        required=False,
        min_value=0,
        max_digits=12,
        decimal_places=2,
        help_text=(
            "Leave blank if unknown. "
            "Enter 0 if the resource is free."
        ),
        widget=forms.NumberInput(
            attrs={
                "class": "input",
                "min": "0",
                "max": "9999999999.99",
                "step": "0.01",
            }
        ),
    )

    currency = forms.CharField(
        label="Currency",
        max_length=3,
        required=False,
        help_text="Three letters, for example USD.",
        widget=forms.TextInput(
            attrs={
                "class": "input",
                "placeholder": "USD",
                "maxlength": "3",
            }
        ),
    )

    expected_revision = forms.IntegerField(
        min_value=1,
        widget=forms.HiddenInput(),
    )

    def clean_currency(self):
        currency = self.cleaned_data["currency"].upper()

        if currency and (
            len(currency) != 3
            or not all("A" <= character <= "Z" for character in currency)
        ):
            raise forms.ValidationError(
                "Use three currency letters, for example USD."
            )

        return currency

    def clean(self):
        cleaned_data = super().clean()

        cost_amount = cleaned_data.get("cost_amount")
        currency = cleaned_data.get("currency")

        if (
            "cost_amount" in self.errors
            or "currency" in self.errors
        ):
            return cleaned_data

        if cost_amount is not None and not currency:
            self.add_error(
                "currency",
                "Enter a currency when a cost is provided.",
            )

        if currency and cost_amount is None:
            self.add_error(
                "cost_amount",
                "Enter a cost when a currency is provided.",
            )

        return cleaned_data
