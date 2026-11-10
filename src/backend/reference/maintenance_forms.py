from django import forms

from .models import ContentKind


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