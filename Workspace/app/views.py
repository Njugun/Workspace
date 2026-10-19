"""
Definition of views.
"""

from django.shortcuts import render, redirect
from django.contrib.auth import login
from .forms import SignUpForm
from workspaces.services import create_workspace
from datetime import datetime
from django.http import HttpRequest

def home(request):
    """Renders the home page."""
    assert isinstance(request, HttpRequest)
    return render(
        request,
        'app/index.html',
        {
            'title':'Home Page',
            'year':datetime.now().year,
        }
    )

def signup(request):
    """Lets a visitor create an account."""
    if request.user.is_authenticated:
        return redirect('home')
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            create_workspace(user, f"{user.username}'s Workspace")
            return redirect('home')
    else:
        form = SignUpForm()
    return render(request, 'app/signup.html', {'form': form, 'title': 'Sign up'})

