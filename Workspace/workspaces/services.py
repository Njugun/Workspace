from django.db import transaction

from .models import Block, Membership, Workspace


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