from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from .forms import PageForm, WorkspaceForm
from .models import Block, Page
from .permissions import (
    can_edit,
    get_block_and_membership,
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


@login_required
@require_POST
def block_toggle(request, pk):
   """Ticks or unticks a to-do block and returns the updated block as an HTML snippet."""
   block, membership = get_block_and_membership(request.user, pk)
   require_editor(membership)
   if block.kind != Block.Kind.TODO:
       return HttpResponseBadRequest('Only to-do blocks can be ticked.')
   block.checked = 'checked' in request.POST
   block.save(update_fields=['checked', 'updated_at'])
   return render(request, 'workspaces/_block.html', {'block': block, 'can_edit': True})