"""Email sign-in using Django's existing credential validation."""
from django import forms
from django.contrib.auth.forms import AuthenticationForm


class EmailAuthenticationForm(AuthenticationForm):
    # AuthenticationForm uses this internal field name with USERNAME_FIELD.
    # The label/widget identify it as email; no username column is required.
    username = forms.EmailField(
        label="Email address", max_length=254,
        widget=forms.EmailInput(attrs={"autofocus": True, "autocomplete": "username"}),
    )

    def clean_username(self):
        return self.cleaned_data["username"].strip().lower()
