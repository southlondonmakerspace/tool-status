from django import forms


class ReportProblemForm(forms.Form):
    latest_issue = forms.CharField(
        label="Something wrong? Describe the problem",
        max_length=2000,
        widget=forms.Textarea(attrs={"rows": 4, "placeholder": "For example: blade guard is loose"}),
        error_messages={"required": "Describe the problem so the next person knows what's wrong."},
    )
