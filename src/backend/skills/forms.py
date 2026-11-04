from django import forms
from reference.selectors import latest_available
from .models import ProficiencyLevel, Skill

INPUT = {"class": "input"}


class SkillForm(forms.Form):
    skill = forms.ModelChoiceField(queryset=Skill.objects.filter(status="active"), widget=forms.Select(attrs=INPUT))
    level = forms.TypedChoiceField(choices=ProficiencyLevel.choices, coerce=int, widget=forms.Select(attrs=INPUT))
    evidence = forms.CharField(required=False, max_length=4000, widget=forms.Textarea(attrs={**INPUT, "rows": 2}))


class LevelForm(forms.Form):
    level = forms.TypedChoiceField(choices=ProficiencyLevel.choices, coerce=int)


class CourseForm(forms.Form):
    course = forms.ModelChoiceField(queryset=latest_available("course"), widget=forms.Select(attrs=INPUT))
