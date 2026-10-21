import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from .models import Membership

# Who has each page open right now: {page id: {connection name: (user id, username)}}.
# This lives in this server process only (decision O1). At deployment, when there may
# be several processes, it moves to Redis.
_present = {}


def people_on(page_id):
    """Usernames of the people on a page, each listed once however many tabs they have open."""
    names = {user_id: name for user_id, name in _present.get(page_id, {}).values()}
    return sorted(names.values(), key=str.lower)


class PageConsumer(AsyncWebsocketConsumer):
    """One open browser tab looking at one page. It only listens for announcements."""

    async def connect(self):
        self.joined = False
        self.page_id = self.scope['url_route']['kwargs']['page_id']
        user = self.scope['user']
        workspace_id = await self.workspace_id_if_member(user) if user.is_authenticated else None
        if workspace_id is None:
            await self.close()  # refuse the connection
            return

        self.user = user
        self.group_name = f'page_{self.page_id}'
        self.workspace_group = f'workspace_{workspace_id}'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.channel_layer.group_add(self.workspace_group, self.channel_name)
        await self.accept()
        self.joined = True
        _present.setdefault(self.page_id, {})[self.channel_name] = (user.pk, user.get_username())
        await self.announce_presence()

    async def disconnect(self, code):
        if not getattr(self, 'joined', False):
            return
        self.joined = False
        await self.channel_layer.group_discard(self.group_name, self.channel_name)
        await self.channel_layer.group_discard(self.workspace_group, self.channel_name)
        here = _present.get(self.page_id)
        if here is not None and here.pop(self.channel_name, None) is not None:
            if not here:
                del _present[self.page_id]
            await self.announce_presence()

    async def announce_presence(self):
        await self.channel_layer.group_send(self.group_name, {
            'type': 'page_event',
            'payload': {'action': 'presence', 'page_id': self.page_id, 'users': people_on(self.page_id)},
        })

    async def page_event(self, event):
        # Called when something is announced to this page's group.
        await self.send(text_data=json.dumps(event['payload']))

    async def membership_event(self, event):
        # Called when someone's place in this workspace changed. Only their own tabs react.
        if event['user_id'] != self.user.pk:
            return
        if event['action'] == 'removed' and await self.workspace_id_if_member(self.user) is None:
            await self.close(code=4403)   # the page reads this code and goes back to Home
            return
        await self.send(text_data=json.dumps({'action': 'reload', 'page_id': self.page_id}))

    @database_sync_to_async
    def workspace_id_if_member(self, user):
        membership = Membership.objects.filter(user=user, workspace__pages__pk=self.page_id).first()
        return membership.workspace_id if membership else None