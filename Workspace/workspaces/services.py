from django.db.models import F
from django.utils import timezone

from django.contrib.auth import get_user_model

from django.db import transaction

from .models import Block, Membership, Page, Workspace


@transaction.atomic
def create_workspace(user, name):
    """Creates a workspace and makes `user` its owner. Both happen, or neither does."""
    workspace = Workspace.objects.create(name=name)
    Membership.objects.create(workspace=workspace, user=user, role=Membership.Role.OWNER)
    return workspace


MIN_GAP = 1e-6


def _renumber(blocks):
    """Gives the blocks positions 1, 2, 3... keeping their current order."""
    for index, block in enumerate(blocks, start=1):
        block.position = float(index)
    Block.objects.bulk_update(blocks, ['position'])


def _midpoint(lower, upper):
    """A position between two neighbours. Either can be None at the top or bottom of a page."""
    if lower is None and upper is None:
        return 1.0
    if lower is None:
        return upper - 1
    if upper is None:
        return lower + 1
    return (lower + upper) / 2


@transaction.atomic
def place_block(block, above_pk, below_pk):
    """Puts a block between two neighbours on its page (None means the top or bottom edge).

    Normally only the moved block is saved. If the neighbours are too close together,
    the whole page is renumbered first. Returns False if a neighbour is not on this page.
    """
    blocks = sorted(block.page.blocks.select_for_update(), key=lambda b: (b.position, b.pk))
    by_pk = {b.pk: b for b in blocks}
    if block.pk in (above_pk, below_pk):
        return False
    if above_pk is not None and above_pk == below_pk:
        return False
    if any(pk is not None and pk not in by_pk for pk in (above_pk, below_pk)):
        return False

    def bounds():
        lower = by_pk[above_pk].position if above_pk is not None else None
        upper = by_pk[below_pk].position if below_pk is not None else None
        return lower, upper

    lower, upper = bounds()
    if lower is not None and upper is not None and abs(upper - lower) < MIN_GAP:
        _renumber(blocks)
        lower, upper = bounds()

    moving = by_pk[block.pk]
    moving.position = _midpoint(lower, upper)
    moving.save(update_fields=['position', 'updated_at'])
    return True


@transaction.atomic
def move_block(block, direction):
    """Moves a block one place up or down. Returns False if it is already at that edge."""
    blocks = sorted(block.page.blocks.all(), key=lambda b: (b.position, b.pk))
    pks = [b.pk for b in blocks]
    index = pks.index(block.pk)
    if direction == 'up':
        if index == 0:
            return False
        above = pks[index - 2] if index >= 2 else None
        below = pks[index - 1]
    else:
        if index == len(pks) - 1:
            return False
        above = pks[index + 1]
        below = pks[index + 2] if index + 2 < len(pks) else None
    return place_block(block, above, below)



def save_block_text(block_pk, text, version=None, original=None):
    """Saves new text unless the block changed since the person opened it.

    Returns (outcome, block) where outcome is:
      'saved'     the text was saved and the version went up by one
      'unchanged' there was nothing to save
      'conflict'  someone else saved first, so nothing was written

    `version` is the version the person opened. `original` is the text they opened.
    If either is missing (an older client), the save goes through without the check.
    """
    current = Block.objects.get(pk=block_pk)
    if text == current.text:
        return 'unchanged', current
    if original is not None and text == original:
        return 'unchanged', current   # they changed nothing, so don't overwrite someone else's edit

    changes = Block.objects.filter(pk=block_pk)
    if version is not None:
        changes = changes.filter(version=version)   # only matches if nobody saved in between
    saved = changes.update(text=text, version=F('version') + 1, updated_at=timezone.now())
    current = Block.objects.get(pk=block_pk)
    return ('saved' if saved else 'conflict'), current


class MembershipError(Exception):
    """A membership change that is not allowed. The message is safe to show to the person."""


def _check_role(role):
    if role not in Membership.Role.values:
        raise MembershipError('Unknown role.')


def _check_not_last_owner(membership):
    """Refuses to lose the workspace's only owner."""
    if membership.role != Membership.Role.OWNER:
        return
    owners = list(
        Membership.objects.select_for_update().filter(
            workspace_id=membership.workspace_id, role=Membership.Role.OWNER
        )
    )
    if len(owners) <= 1:
        raise MembershipError('A workspace needs at least one owner.')


@transaction.atomic
def add_member(workspace, username, role):
    """Adds an existing account to a workspace. Returns the new Membership."""
    _check_role(role)
    User = get_user_model()
    username = (username or '').strip()
    user = None
    if username:
        user = User.objects.filter(**{f'{User.USERNAME_FIELD}__iexact': username}).first()
    if user is None:
        raise MembershipError('There is no account with that username.')
    if Membership.objects.filter(workspace=workspace, user=user).exists():
        raise MembershipError(f'{user.get_username()} is already a member.')
    return Membership.objects.create(workspace=workspace, user=user, role=role)


@transaction.atomic
def change_role(membership, role):
    """Gives a member a new role. The last owner cannot be demoted."""
    _check_role(role)
    membership = Membership.objects.select_for_update().get(pk=membership.pk)
    if role != Membership.Role.OWNER:
        _check_not_last_owner(membership)
    membership.role = role
    membership.save(update_fields=['role'])
    return membership


@transaction.atomic
def remove_member(membership):
    """Removes a member from a workspace, or lets them leave. The last owner cannot go."""
    membership = Membership.objects.select_for_update().get(pk=membership.pk)
    _check_not_last_owner(membership)
    membership.delete()




MAX_PAGE_DEPTH = 4
MAX_TITLE_LENGTH = 200


class PageError(Exception):
    """A page change that is not allowed. The message is safe to show to the person."""


def _clean_title(title):
    title = (title or '').strip()
    if not title:
        raise PageError('A page needs a title.')
    if len(title) > MAX_TITLE_LENGTH:
        raise PageError(f'A title can be at most {MAX_TITLE_LENGTH} characters.')
    return title


def page_depth(page):
    """How deep a page sits: 1 for a top-level page, 2 for a sub-page, and so on."""
    depth = 1
    while page.parent_id is not None:
        page = Page.objects.get(pk=page.parent_id)
        depth += 1
    return depth


@transaction.atomic
def create_page(workspace, title, created_by, parent=None):
    """Creates a page, at the top level or inside `parent`. Returns the new Page."""
    title = _clean_title(title)
    if parent is not None:
        if parent.workspace_id != workspace.pk:
            raise PageError('A sub-page must be in the same workspace as its parent.')
        if page_depth(parent) >= MAX_PAGE_DEPTH:
            raise PageError(f'Pages can be nested {MAX_PAGE_DEPTH} levels deep at most.')
    return Page.objects.create(workspace=workspace, parent=parent, title=title, created_by=created_by)


def rename_page(page, title):
    """Gives a page a new title. Returns the page."""
    page.title = _clean_title(title)
    page.save(update_fields=['title', 'updated_at'])
    return page


def descendant_ids(page):
    """The ids of every page nested inside `page`, at any depth."""
    found, frontier = [], [page.pk]
    while frontier:
        frontier = list(Page.objects.filter(parent_id__in=frontier).values_list('pk', flat=True))
        found.extend(frontier)
    return found


def deletion_summary(page):
    """(pages, blocks) that deleting `page` would remove, counting the page and everything inside it."""
    page_ids = [page.pk] + descendant_ids(page)
    return len(page_ids), Block.objects.filter(page_id__in=page_ids).count()


@transaction.atomic
def delete_page(page):
    """Deletes a page with its blocks and sub-pages. Returns the ids of every page removed."""
    page_ids = [page.pk] + descendant_ids(page)
    page.delete()
    return page_ids