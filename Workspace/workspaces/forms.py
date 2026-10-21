from django import forms
from .models import Membership

INPUT_CLASSES = (
    'mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm '
    'focus:border-slate-500 focus:outline-none focus:ring-1 focus:ring-slate-500'
)


class WorkspaceForm(forms.Form):
    name = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={'class': INPUT_CLASSES, 'autofocus': True}),
    )


class PageForm(forms.Form):
    title = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={'class': INPUT_CLASSES, 'autofocus': True}),
    )


class AddMemberForm(forms.Form):
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={'class': INPUT_CLASSES, 'autofocus': True, 'placeholder': 'Username'}),
    )
    role = forms.ChoiceField(
        choices=Membership.Role.choices,
        initial=Membership.Role.EDITOR,
        widget=forms.Select(attrs={'class': INPUT_CLASSES}),
    )