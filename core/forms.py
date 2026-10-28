from django import forms
from django.contrib.auth import password_validation

from .models import SKILL_LEVELS, Account, CareerProfile, Skill, Student, UniversityCourse

INPUT = {"class": "input"}


class RegisterForm(forms.Form):
    """Registration accepts exactly these fields (blueprint §5.1). Anything else
    the browser sends, such as role or student_id, is never read."""

    name = forms.CharField(max_length=80, widget=forms.TextInput(attrs={**INPUT, "autocomplete": "name"}))
    email = forms.EmailField(max_length=254, widget=forms.EmailInput(attrs={**INPUT, "autocomplete": "email"}))
    major = forms.CharField(max_length=80, required=False, widget=forms.TextInput(attrs={**INPUT, "placeholder": "Computer Science"}))
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={**INPUT, "autocomplete": "new-password"}),
        help_text="At least 10 characters. Avoid common passwords.",
    )
    password_confirm = forms.CharField(
        label="Confirm password", widget=forms.PasswordInput(attrs={**INPUT, "autocomplete": "new-password"})
    )

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if Account.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists. Try signing in.")
        return email

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if not name:
            raise forms.ValidationError("Enter your name.")
        return name

    def clean(self):
        data = super().clean()
        pw, pw2 = data.get("password"), data.get("password_confirm")
        if pw and pw2 and pw != pw2:
            self.add_error("password_confirm", "The passwords don't match.")
        if pw:
            probe = Account(email=data.get("email") or "")
            try:
                password_validation.validate_password(pw, probe)
            except forms.ValidationError as e:
                self.add_error("password", e)
        return data


class LoginForm(forms.Form):
    email = forms.EmailField(widget=forms.EmailInput(attrs={**INPUT, "autocomplete": "email", "autofocus": True}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={**INPUT, "autocomplete": "current-password"}))


class ProfileForm(forms.ModelForm):
    class Meta:
        model = Student
        fields = list(Student.EDITABLE_FIELDS)
        widgets = {
            "name": forms.TextInput(attrs=INPUT),
            "major": forms.TextInput(attrs=INPUT),
            "career_interests": forms.TextInput(attrs={**INPUT, "placeholder": "Cloud engineering, security, data"}),
        }


class SkillForm(forms.Form):
    skill = forms.ModelChoiceField(queryset=Skill.objects.all(), widget=forms.Select(attrs=INPUT))
    level = forms.TypedChoiceField(choices=SKILL_LEVELS, coerce=int, widget=forms.Select(attrs=INPUT))
    evidence = forms.CharField(
        max_length=240,
        required=False,
        widget=forms.TextInput(attrs={**INPUT, "placeholder": "e.g. Built a Flask API for my CSC 325 project"}),
    )


class CourseForm(forms.Form):
    course = forms.ModelChoiceField(queryset=UniversityCourse.objects.all(), widget=forms.Select(attrs=INPUT))
    term = forms.CharField(max_length=20, required=False, widget=forms.TextInput(attrs={**INPUT, "placeholder": "Fall 2026"}))


class ResumeForm(forms.Form):
    resume = forms.FileField(
        widget=forms.ClearableFileInput(attrs={"accept": ".pdf,.docx,.txt", "class": "file-input"})
    )


class PostingForm(forms.Form):
    title = forms.CharField(max_length=100, widget=forms.TextInput(attrs={**INPUT, "placeholder": "Junior Cloud Engineer"}))
    company = forms.CharField(max_length=80, widget=forms.TextInput(attrs={**INPUT, "placeholder": "Company name"}))
    description = forms.CharField(
        min_length=80,
        max_length=20000,
        widget=forms.Textarea(
            attrs={**INPUT, "rows": 12, "placeholder": "Paste the full posting, including the Requirements and Preferred sections."}
        ),
    )


class CareerChoiceForm(forms.Form):
    career = forms.ModelChoiceField(queryset=CareerProfile.objects.filter(is_published=True))
