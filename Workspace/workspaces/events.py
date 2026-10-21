from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction


def announce(page_id, action, block_id=None):
    """Tells every browser that has this page open that something changed.

    The message goes out only after the database change is saved, so a browser that
    reacts instantly never fetches the old version. It carries no content, only
    what happened and which block, and each browser fetches its own copy.
    """
    payload = {'action': action, 'page_id': page_id, 'block_id': block_id}

    def send():
        async_to_sync(get_channel_layer().group_send)(
            f'page_{page_id}',
            {'type': 'page_event', 'payload': payload},
        )

    transaction.on_commit(send)

def announce_membership(workspace_id, user_id, action):
    """Tells one person's open pages that their place in a workspace changed.

    `action` is 'removed' or 'role'. Every open page in the workspace hears the message,
    and each one ignores it unless it belongs to that person.
    """
    def send():
        async_to_sync(get_channel_layer().group_send)(
            f'workspace_{workspace_id}',
            {'type': 'membership_event', 'user_id': user_id, 'action': action},
        )

    transaction.on_commit(send)
