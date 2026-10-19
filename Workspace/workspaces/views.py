from django.contrib.auth.decorators import login_required
from django.db.models import Max
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST

from .forms import PageForm, WorkspaceForm
from .models import Block, Page
from .permissions import (
    can_edit,
    get_block_and_membership,
    get_page_and_membership,
    membership_for_workspace,
    require_editor,
)
from .services import create_workspace, move_block, place_block


@login_required
def page_detail(request, pk):
    """Shows one page and its blocks. Only members of the page's workspace may see it."""
    page, membership = get_page_and_membership(request.user, pk)
    return render(request, 'workspaces/page_detail.html', {
        'page': page,
        'blocks': page.blocks.order_by('position', 'pk'),
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


MAX_BLOCK_TEXT = 5000


@login_required
@require_GET
def block_edit(request, pk):
     """Returns the inline edit form for one block."""
     block, membership = get_block_and_membership(request.user, pk)
     require_editor(membership)
     return render(request, 'workspaces/_block_edit.html', {'block': block})


@login_required
@require_POST
def block_update(request, pk):
     """Saves a block's new text and returns the updated block as an HTML snippet."""
     block, membership = get_block_and_membership(request.user, pk)
     require_editor(membership)
     block.text = request.POST.get('text', '').strip()[:MAX_BLOCK_TEXT]
     block.save(update_fields=['text', 'updated_at'])
     return render(request, 'workspaces/_block.html', {'block': block, 'can_edit': True})


@login_required
@require_POST
def block_create(request, page_pk):
     """Adds an empty block of the chosen kind to the end of a page and returns its edit form."""
     page, membership = get_page_and_membership(request.user, page_pk)
     require_editor(membership)
     kind = request.POST.get('kind')
     if kind not in Block.Kind.values:
         return HttpResponseBadRequest('Unknown block type.')
     last = page.blocks.aggregate(last=Max('position'))['last']
     block = Block.objects.create(page=page, kind=kind, position=1 if last is None else last + 1)
     return render(request, 'workspaces/_block_edit.html', {'block': block})

@login_required
@require_POST
def block_delete(request, pk):
    """Deletes a block. The empty reply tells HTMX to remove it from the page."""
    block, membership = get_block_and_membership(request.user, pk)
    require_editor(membership)
    block.delete()
    return HttpResponse('')


@login_required
@require_POST
def block_move(request, pk):
     """Moves a block up or down and returns the page's refreshed block list."""
     block, membership = get_block_and_membership(request.user, pk)
     require_editor(membership)
     direction = request.POST.get('direction')
     if direction not in ('up', 'down'):
         return HttpResponseBadRequest('Direction must be up or down.')
     move_block(block, direction)
     return render(request, 'workspaces/_block_list.html', {
         'blocks': block.page.blocks.order_by('position', 'pk'),
         'can_edit': True,
     })


def _optional_pk(value):
     """'' or missing means None, a number means that number. Anything else raises ValueError."""
     return int(value) if value else None


@login_required
@require_POST
def block_reorder(request, pk):
     """Drag and drop: puts a block between the two neighbours it was dropped between."""
     block, membership = get_block_and_membership(request.user, pk)
     require_editor(membership)
     try:
         above = _optional_pk(request.POST.get('above'))
         below = _optional_pk(request.POST.get('below'))
     except ValueError:
         return HttpResponseBadRequest('Neighbours must be block numbers.')
     if not place_block(block, above, below):
         return HttpResponseBadRequest('Those blocks are not neighbours on this page.')
     return HttpResponse(status=204)