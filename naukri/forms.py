from django import forms


class SearchForm(forms.Form):
    keyword = forms.CharField(
        max_length=200,
        required=True,
        widget=forms.TextInput(
            attrs={
                "placeholder": "Job title, skills, or company...",
                "class": "search-input",
                "autocomplete": "off",
                "autofocus": True,
            }
        ),
        label="",
        error_messages={"required": "Please enter a keyword to search."},
    )
