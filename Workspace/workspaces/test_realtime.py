from asgiref.sync import sync_to_async
from channels.testing import WebsocketCommunicator
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse

from Workspace.asgi import application

from .models import Block, Membership, Page
from .services import create_workspace

User = get_user_model()


class WorldMixin:
    """One workspace with an owner, an editor and a viewer, plus an outsider and two pages."""

    def build_world(self):
        self.owner = User.objects.create_user('owner')
        self.editor = User.objects.create_user('editor')
        self.viewer = User.objects.create_user('viewer')
        self.outsider = User.objects.create_user('outsider')

        self.workspace = create_workspace(self.owner, 'Team')
        Membership.objects.create(workspace=self.workspace, user=self.editor, role=Membership.Role.EDITOR)
        Membership.objects.create(workspace=self.workspace, user=self.viewer, role=Membership.Role.VIEWER)

        self.page = Page.objects.create(workspace=self.workspace, title='Main', created_by=self.owner)
        self.other_page = Page.objects.create(workspace=self.workspace, title='Other', created_by=self.owner)

        self.heading = Block.objects.create(page=self.page, kind=Block.Kind.HEADING, text='Title', position=1.0)
        self.paragraph = Block.objects.create(page=self.page, kind=Block.Kind.PARAGRAPH, text='Hello', position=2.0)
        self.todo = Block.objects.create(page=self.page, kind=Block.Kind.TODO, text='Task', position=3.0)

        self.owner_client = self.login(self.owner)
        self.editor_client = self.login(self.editor)
        self.viewer_client = self.login(self.viewer)
        self.outsider_client = self.login(self.outsider)
        self.anonymous_client = Client()

    @staticmethod
    def login(user):
        client = Client()
        client.force_login(user)
        return client


class LiveViewsTests(WorldMixin, TestCase):
    """The two read-only views the browsers call after an announcement."""

    def setUp(self):
        self.build_world()
        self.detail_url = reverse('block_detail', args=[self.paragraph.pk])
        self.list_url = reverse('block_list', args=[self.page.pk])

    def test_editor_gets_a_block_with_editing_controls(self):
        response = self.editor_client.get(self.detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Hello')
        self.assertContains(response, 'hx-get')

    def test_viewer_gets_a_block_without_editing_controls(self):
        response = self.viewer_client.get(self.detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Hello')
        self.assertNotContains(response, 'hx-get')
        self.assertNotContains(response, 'hx-post')

    def test_outsider_cannot_fetch_a_block(self):
        self.assertEqual(self.outsider_client.get(self.detail_url).status_code, 404)

    def test_anonymous_user_cannot_fetch_a_block(self):
        self.assertEqual(self.anonymous_client.get(self.detail_url).status_code, 302)

    def test_editor_gets_the_block_list_with_editing_controls(self):
        response = self.editor_client.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        for text in ('Title', 'Hello', 'Task'):
            self.assertContains(response, text)
        self.assertContains(response, 'hx-get')

    def test_viewer_gets_the_block_list_without_editing_controls(self):
        response = self.viewer_client.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Hello')
        self.assertNotContains(response, 'hx-get')
        self.assertNotContains(response, 'hx-post')

    def test_outsider_cannot_fetch_the_block_list(self):
        self.assertEqual(self.outsider_client.get(self.list_url).status_code, 404)

    def test_anonymous_user_cannot_fetch_the_block_list(self):
        self.assertEqual(self.anonymous_client.get(self.list_url).status_code, 302)


class RealtimeTests(WorldMixin, TransactionTestCase):
    """The WebSocket: who may connect, and what gets announced to whom.

    These go through the real application from asgi.py, including the origin check
    and the session login, and they use the real views to cause the announcements.
    """

    def setUp(self):
        self.build_world()

    def socket(self, page_id, client=None, origin=b'http://testserver'):
        headers = [(b'origin', origin)]
        if client is not None:
            name = settings.SESSION_COOKIE_NAME
            headers.append((b'cookie', f'{name}={client.cookies[name].value}'.encode()))
        return WebsocketCommunicator(application, f'/ws/pages/{page_id}/', headers=headers)

    async def post_and_receive(self, client, url, data=None, listener=None):
        """Has a member listening, makes the change through the real view, returns both results."""
        comm = self.socket(self.page.pk, listener or self.viewer_client)
        try:
            connected, _ = await comm.connect()
            self.assertTrue(connected)
            await comm.receive_json_from(timeout=2)   # skip the "who is here" message
            response = await sync_to_async(client.post)(url, data or {})
            message = await comm.receive_json_from(timeout=2)
            return response, message
        finally:
            await comm.disconnect()

    # --- who may connect ---

    async def test_owner_can_connect(self):
        comm = self.socket(self.page.pk, self.owner_client)
        connected, _ = await comm.connect()
        self.assertTrue(connected)
        await comm.disconnect()

    async def test_viewer_can_connect(self):
        comm = self.socket(self.page.pk, self.viewer_client)
        connected, _ = await comm.connect()
        self.assertTrue(connected)
        await comm.disconnect()

    async def test_outsider_is_refused(self):
        comm = self.socket(self.page.pk, self.outsider_client)
        connected, _ = await comm.connect()
        self.assertFalse(connected)

    async def test_anonymous_user_is_refused(self):
        comm = self.socket(self.page.pk)
        connected, _ = await comm.connect()
        self.assertFalse(connected)

    async def test_missing_page_is_refused(self):
        comm = self.socket(999999, self.owner_client)
        connected, _ = await comm.connect()
        self.assertFalse(connected)

    async def test_connection_from_another_website_is_refused(self):
        comm = self.socket(self.page.pk, self.owner_client, origin=b'http://evil.example')
        connected, _ = await comm.connect()
        self.assertFalse(connected)

    # --- what gets announced ---

    async def test_editing_a_block_is_announced(self):
        response, message = await self.post_and_receive(
            self.editor_client, reverse('block_update', args=[self.paragraph.pk]), {'text': 'Changed'},
        )
        self.assertEqual(response.status_code, 200)
        # Only what happened and which block: never the content itself.
        self.assertEqual(message, {'action': 'updated', 'page_id': self.page.pk, 'block_id': self.paragraph.pk})

    async def test_ticking_a_todo_is_announced(self):
        response, message = await self.post_and_receive(
            self.editor_client, reverse('block_toggle', args=[self.todo.pk]), {'checked': 'on'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(message, {'action': 'updated', 'page_id': self.page.pk, 'block_id': self.todo.pk})

    async def test_adding_a_block_is_announced(self):
        response, message = await self.post_and_receive(
            self.editor_client, reverse('block_create', args=[self.page.pk]), {'kind': 'paragraph'},
        )
        self.assertEqual(response.status_code, 200)
        newest = await sync_to_async(lambda: Block.objects.latest('pk').pk)()
        self.assertEqual(message, {'action': 'created', 'page_id': self.page.pk, 'block_id': newest})

    async def test_deleting_a_block_announces_the_deleted_blocks_number(self):
        deleted_pk = self.paragraph.pk
        response, message = await self.post_and_receive(
            self.editor_client, reverse('block_delete', args=[deleted_pk]),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(message, {'action': 'deleted', 'page_id': self.page.pk, 'block_id': deleted_pk})

    async def test_moving_a_block_with_the_buttons_is_announced(self):
        response, message = await self.post_and_receive(
            self.editor_client, reverse('block_move', args=[self.paragraph.pk]), {'direction': 'down'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(message, {'action': 'reordered', 'page_id': self.page.pk, 'block_id': self.paragraph.pk})

    async def test_dragging_a_block_is_announced(self):
        response, message = await self.post_and_receive(
            self.editor_client, reverse('block_reorder', args=[self.heading.pk]),
            {'above': str(self.todo.pk), 'below': ''},
        )
        self.assertEqual(response.status_code, 204)
        self.assertEqual(message, {'action': 'reordered', 'page_id': self.page.pk, 'block_id': self.heading.pk})

    # --- what must not be announced ---

    async def test_a_refused_change_announces_nothing(self):
        comm = self.socket(self.page.pk, self.owner_client)
        try:
            connected, _ = await comm.connect()
            self.assertTrue(connected)
            await comm.receive_json_from(timeout=2)   # skip the "who is here" message
            response = await sync_to_async(self.viewer_client.post)(
                reverse('block_update', args=[self.paragraph.pk]), {'text': 'Hacked'},
            )
            self.assertEqual(response.status_code, 403)
            self.assertTrue(await comm.receive_nothing(timeout=0.3))
        finally:
            await comm.disconnect()

    async def test_other_pages_hear_nothing(self):
        comm = self.socket(self.other_page.pk, self.owner_client)
        try:
            connected, _ = await comm.connect()
            self.assertTrue(connected)
            await comm.receive_json_from(timeout=2)   # skip the "who is here" message
            await sync_to_async(self.editor_client.post)(
                reverse('block_update', args=[self.paragraph.pk]), {'text': 'Changed'},
            )
            self.assertTrue(await comm.receive_nothing(timeout=0.3))
        finally:
            await comm.disconnect()
