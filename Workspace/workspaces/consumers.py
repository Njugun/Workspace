import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from .models import Membership


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

    async def disconnect(self, code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def page_event(self, event):
        # Called when something is announced to this page's group (6c does the announcing).
        await self.send(text_data=json.dumps(event['payload']))

    @database_sync_to_async
    def is_member(self, user):
        return Membership.objects.filter(user=user, workspace__pages__pk=self.page_id).exists()
