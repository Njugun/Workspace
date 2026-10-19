from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .forms import PageForm, WorkspaceForm
from .models import Page
from .permissions import (
    can_edit,
    get_page_and_membership,
    membership_for_workspace,
    require_editor,
)
from .services import create_workspace


@login_required
def page_detail(request, pk):
    """Shows one page and its blocks. Only members of the page's workspace may see it."""
    page, membership = get_page_and_membership(request.user, pk)
    return render(request, 'workspaces/page_detail.html', {
        'page': page,
        'blocks': page.blocks.all(),
        'can_edit': can_edit(membership),
        'title': page.title,
    })


@login_required
def workspace_create(request):
    """Any signed-in user may create a workspace and becomes its owner."""
    if request.method == 'POST':
        form = WorkspaceForm(request.POST)
        if form.is_valid():
            create_workspace(request.user, form.cleaned_data['name'])
            return redirect('home')
    else:
        form = WorkspaceForm()
    return render(request, 'workspaces/form.html', {
        'form': form,
        'title': 'New workspace',
        'heading': 'Create a workspace',
        'button': 'Create workspace',
    })


@login_required
def page_create(request, workspace_id):
    """Owners and editors may add pages. Non-members get a 404, viewers a 403."""
    membership = membership_for_workspace(request.user, workspace_id)
    require_editor(membership)
    if request.method == 'POST':
        form = PageForm(request.POST)
        if form.is_valid():
            page = Page.objects.create(
                workspace=membership.workspace,
                title=form.cleaned_data['title'],
                created_by=request.user,
            )
            return redirect('page_detail', pk=page.pk)
    else:
        form = PageForm()
    return render(request, 'workspaces/form.html', {
        'form': form,
        'title': 'New page',
        'heading': f'New page in {membership.workspace.name}',
        'button': 'Create page',
    })