from django.contrib.auth.decorators import login_required
from django.db.models import Max
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .events import announce, announce_membership
from .forms import AddMemberForm, PageForm, WorkspaceForm
from .models import Block, Membership, Page
from .permissions import (
    can_edit,
    get_block_and_membership,
    get_page_and_membership,
    membership_for_workspace,
    require_editor,
    require_owner,
)
from .services import (
    MembershipError,
    PageError,
    add_member,
    ancestors,
    change_role,
    create_page,
    create_workspace,
    delete_page,
    deletion_summary,
    move_block,
    place_block,
    remove_member,
    rename_page,
    save_block_text,
)




@login_required
def page_detail(request, pk):
    """Shows one page and its blocks. Only members of the page's workspace may see it."""
    page, membership = get_page_and_membership(request.user, pk)
    return render(request, 'workspaces/page_detail.html', {
        'page': page,
        'ancestors': ancestors(page),
        'blocks': page.blocks.order_by('position', 'pk'),
        'can_edit': can_edit(membership),
        'is_owner': membership.role == Membership.Role.OWNER,
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
            page = create_page(membership.workspace, form.cleaned_data['title'], request.user)
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
@require_GET
def block_detail(request, pk):
    """Returns one block as an HTML snippet, as this viewer's role is allowed to see it."""
    block, membership = get_block_and_membership(request.user, pk)
    return render(request, 'workspaces/_block.html', {
        'block': block,
        'can_edit': can_edit(membership),
    })


@login_required
@require_GET
def block_list(request, page_pk):
    """Returns a page's whole block list, as this viewer's role is allowed to see it."""
    page, membership = get_page_and_membership(request.user, page_pk)
    return render(request, 'workspaces/_block_list.html', {
        'blocks': page.blocks.order_by('position', 'pk'),
        'can_edit': can_edit(membership),
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
    announce(block.page_id, 'updated', block.pk)
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
    """Saves a block's new text, unless someone else changed the block in the meantime."""
    block, membership = get_block_and_membership(request.user, pk)
    require_editor(membership)
    text = request.POST.get('text', '').strip()[:MAX_BLOCK_TEXT]
    try:
        version = _optional_pk(request.POST.get('version'))
    except ValueError:
        return HttpResponseBadRequest('Version must be a number.')
    outcome, current = save_block_text(block.pk, text, version, request.POST.get('original'))
    if outcome == 'conflict':
        return render(request, 'workspaces/_block_conflict.html', {'block': current, 'draft': text})
    if outcome == 'saved':
        announce(current.page_id, 'updated', current.pk)
    return render(request, 'workspaces/_block.html', {'block': current, 'can_edit': True})



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
    announce(page.pk, 'created', block.pk)
    return render(request, 'workspaces/_block_edit.html', {'block': block})


@login_required
@require_POST
def block_delete(request, pk):
    """Deletes a block. The empty reply tells HTMX to remove it from the page."""
    block, membership = get_block_and_membership(request.user, pk)
    require_editor(membership)
    page_id, block_id = block.page_id, block.pk  # delete() clears block.pk, so save it first
    block.delete()
    announce(page_id, 'deleted', block_id)
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
    announce(block.page_id, 'reordered', block.pk)
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
    announce(block.page_id, 'reordered', block.pk)
    return HttpResponse(status=204)


def _members_page(request, membership, form=None, error=None, status=200):
    """Draws the Members page for the workspace that `membership` belongs to."""
    workspace = membership.workspace
    members = sorted(
        workspace.memberships.select_related('user'),
        key=lambda m: m.user.get_username().lower(),
    )
    return render(request, 'workspaces/members.html', {
        'workspace': workspace,
        'members': members,
        'is_owner': membership.role == Membership.Role.OWNER,
        'me_id': request.user.pk,
        'roles': Membership.Role.choices,
        'form': form or AddMemberForm(),
        'error': error,
        'title': 'Members',
    }, status=status)


@login_required
def members(request, workspace_id):
    """Lists a workspace's members. Any member may look; only owners get the controls."""
    membership = membership_for_workspace(request.user, workspace_id)
    return _members_page(request, membership)


@login_required
@require_POST
def member_add(request, workspace_id):
    """Owners add an existing account to the workspace."""
    membership = membership_for_workspace(request.user, workspace_id)
    require_owner(membership)
    form = AddMemberForm(request.POST)
    if not form.is_valid():
        return _members_page(request, membership, form=form, status=400)
    try:
        add_member(membership.workspace, form.cleaned_data['username'], form.cleaned_data['role'])
    except MembershipError as error:
        return _members_page(request, membership, form=form, error=str(error), status=400)
    return redirect('members', workspace_id=workspace_id)



@login_required
@require_POST
def member_role(request, workspace_id, pk):
    """Owners change a member's role."""
    membership = membership_for_workspace(request.user, workspace_id)
    require_owner(membership)
    target = get_object_or_404(Membership, pk=pk, workspace_id=workspace_id)
    role = request.POST.get('role', '')
    changed = target.role != role
    try:
        change_role(target, role)
    except MembershipError as error:
        return _members_page(request, membership, error=str(error), status=400)
    if changed:
        announce_membership(workspace_id, target.user_id, 'role')
    return redirect('members', workspace_id=workspace_id)


@login_required
@require_POST
def member_remove(request, workspace_id, pk):
    """Owners remove anyone. Any member may remove themselves, which is leaving."""
    membership = membership_for_workspace(request.user, workspace_id)
    target = get_object_or_404(Membership, pk=pk, workspace_id=workspace_id)
    leaving = target.pk == membership.pk
    if not leaving:
        require_owner(membership)
    user_id = target.user_id
    try:
        remove_member(target)
    except MembershipError as error:
        return _members_page(request, membership, error=str(error), status=400)
    announce_membership(workspace_id, user_id, 'removed')
    if leaving:
        return redirect('home')
    return redirect('members', workspace_id=workspace_id)



@login_required
def subpage_create(request, page_pk):
    """Owners and editors add a page inside an existing page."""
    parent, membership = get_page_and_membership(request.user, page_pk)
    require_editor(membership)
    status = 200
    if request.method == 'POST':
        form = PageForm(request.POST)
        if form.is_valid():
            try:
                page = create_page(parent.workspace, form.cleaned_data['title'], request.user, parent=parent)
            except PageError as error:
                form.add_error('title', str(error))
            else:
                return redirect('page_detail', pk=page.pk)
        status = 400
    else:
        form = PageForm()
    return render(request, 'workspaces/form.html', {
        'form': form,
        'title': 'New sub-page',
        'heading': f'New page inside {parent.title}',
        'button': 'Create page',
    }, status=status)


@login_required
@require_GET
def sidebar_fragment(request):
    """The sidebar on its own, so an open page can refresh it."""
    return render(request, 'workspaces/_sidebar.html')


@login_required
@require_GET
def page_title_edit(request, pk):
    """Returns the inline form for renaming a page."""
    page, membership = get_page_and_membership(request.user, pk)
    require_editor(membership)
    return render(request, 'workspaces/_page_title_edit.html', {'page': page})


@login_required
@require_POST
def page_rename(request, pk):
    """Renames a page and returns the title. An empty title just restores the old one."""
    page, membership = get_page_and_membership(request.user, pk)
    require_editor(membership)
    new_title = request.POST.get('title', '')
    if new_title.strip() != page.title:
        try:
            rename_page(page, new_title)
        except PageError:
            pass
    return render(request, 'workspaces/_page_title.html', {'page': page, 'can_edit': True})


@login_required
@require_http_methods(['GET', 'POST'])
def page_delete(request, pk):
    """Owners only. GET asks for confirmation and says what would go; POST deletes."""
    page, membership = get_page_and_membership(request.user, pk)
    require_owner(membership)
    if request.method == 'POST':
        parent_id = page.parent_id
        delete_page(page)
        if parent_id is not None:
            return redirect('page_detail', pk=parent_id)
        return redirect('home')
    page_count, block_count = deletion_summary(page)
    return render(request, 'workspaces/page_delete.html', {
        'page': page,
        'page_count': page_count,
        'block_count': block_count,
        'title': 'Delete page',
    })