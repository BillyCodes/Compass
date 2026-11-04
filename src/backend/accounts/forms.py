"""Validated email sign-in, registration, and owner-profile forms."""
from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import password_validation
from .models import Account, Student


class EmailAuthenticationForm(AuthenticationForm):
    # AuthenticationForm uses this internal field name with USERNAME_FIELD.
    # The label/widget identify it as email; no username column is required.
    username = forms.EmailField(
        label="Email address", max_length=254,
        widget=forms.EmailInput(attrs={"autofocus": True, "autocomplete": "username", "class": "input"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password"].widget.attrs["class"] = "input"

    def clean_username(self):
        return self.cleaned_data["username"].strip().lower()


class RegistrationForm(forms.Form):
    name = forms.CharField(label="Display name", max_length=150, widget=forms.TextInput(attrs={"class": "input", "autocomplete": "name"}))
    email = forms.EmailField(max_length=254, widget=forms.EmailInput(attrs={"class": "input", "autocomplete": "email"}))
    major = forms.CharField(max_length=150, required=False, widget=forms.TextInput(attrs={"class": "input"}))
    password = forms.CharField(strip=False, widget=forms.PasswordInput(attrs={"class": "input", "autocomplete": "new-password"}))
    password_confirm = forms.CharField(label="Confirm password", strip=False, widget=forms.PasswordInput(attrs={"class": "input", "autocomplete": "new-password"}))

    def clean_email(self):
        email = Account.objects.normalize_email(self.cleaned_data["email"])
        if Account.objects.filter(login_email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean(self):
        data = super().clean()
        password = data.get("password")
        if password and password != data.get("password_confirm"):
            self.add_error("password_confirm", "The passwords must match.")
        if password:
            try:
                password_validation.validate_password(password, Account(login_email=data.get("email", "")))
            except forms.ValidationError as exc:
                self.add_error("password", exc)
        return data


class ProfileForm(forms.ModelForm):
    class Meta:
        model = Student
        fields = ["display_name", "major", "career_interests", "graduation_year"]
        widgets = {"display_name": forms.TextInput(attrs={"class": "input"}),
                   "major": forms.TextInput(attrs={"class": "input"}),
                   "career_interests": forms.Textarea(attrs={"class": "input", "rows": 3}),
                   "graduation_year": forms.NumberInput(attrs={"class": "input"})}
