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

def _neighbours(blocks, index, direction):
     """The positions of the two blocks the moved block must end up between.
      Either can be None when the block is moving to the very top or bottom.
     """
     if direction == 'up':
         lower = blocks[index - 2].position if index >= 2 else None
         upper = blocks[index - 1].position
     else:
         lower = blocks[index + 1].position
         upper = blocks[index + 2].position if index + 2 < len(blocks) else None
     return lower, upper

@transaction.atomic
def move_block(block, direction):
     """Moves a block one place up or down on its page.
     Returns False if the block is already at that edge. Normally only the moved
     block is saved. If its new neighbours are too close together, the whole page
     is renumbered first.
     """
     blocks = sorted(block.page.blocks.select_for_update(), key=lambda b: (b.position, b.pk))
     index = next(i for i, b in enumerate(blocks) if b.pk == block.pk)
     if (direction == 'up' and index == 0) or (direction == 'down' and index == len(blocks) - 1):
         return False
     lower, upper = _neighbours(blocks, index, direction)
     if lower is not None and upper is not None and upper - lower < MIN_GAP:
          _renumber(blocks)
          lower, upper = _neighbours(blocks, index, direction)

     if lower is None:
         new_position = upper - 1
     elif upper is None:
         new_position = lower + 1
     else:
         new_position = (lower + upper) / 2

     moving = blocks[index]
     moving.position = new_position
     moving.save(update_fields=['position', 'updated_at'])
     return True