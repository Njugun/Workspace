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
        self.page_id = self.scope['url_route']['kwargs']['page_id']
        self.group_name = f'page_{self.page_id}'
        user = self.scope['user']

        if not user.is_authenticated or not await self.is_member(user):
            await self.close()  # refuse the connection
            return

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        _present.setdefault(self.page_id, {})[self.channel_name] = (user.pk, user.get_username())
        await self.announce_presence()

    async def disconnect(self, code):
        if not hasattr(self, 'group_name'):
            return
        await self.channel_layer.group_discard(self.group_name, self.channel_name)
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

    @database_sync_to_async
    def is_member(self, user):
        return Membership.objects.filter(user=user, workspace__pages__pk=self.page_id).exists()