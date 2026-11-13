from django import forms

INPUT = {"class": "input"}


class ResumeForm(forms.Form):
    resume = forms.FileField(widget=forms.ClearableFileInput(attrs={"accept": ".pdf,.docx,.txt", "class": "file-input"}))


class PostingForm(forms.Form):
    title = forms.CharField(max_length=100, widget=forms.TextInput(attrs={**INPUT, "placeholder": "Junior Cloud Engineer"}))
    company = forms.CharField(max_length=80, widget=forms.TextInput(attrs={**INPUT, "placeholder": "Company name"}))
    description = forms.CharField(
        min_length=80, max_length=20000,
        widget=forms.Textarea(attrs={**INPUT, "rows": 12, "placeholder": "Paste the full posting, including the Requirements and Preferred sections."}))

    def clean_title(self):
        value = self.cleaned_data["title"].strip()
        if not value:
            raise forms.ValidationError("Enter a job title.")
        return value

    def clean_company(self):
        value = self.cleaned_data["company"].strip()
        if not value:
            raise forms.ValidationError("Enter a company name.")
        return value
