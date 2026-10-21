from asgiref.sync import sync_to_async
from channels.testing import WebsocketCommunicator
from django.conf import settings
from django.test import TransactionTestCase
from django.urls import reverse

from Workspace.asgi import application

from .consumers import _present
from .models import Membership
from .test_realtime import WorldMixin


class MembershipLiveTests(WorldMixin, TransactionTestCase):
    def setUp(self):
        _present.clear()
        self.build_world()
        self.editor_pk = Membership.objects.get(workspace=self.workspace, user=self.editor).pk
        self.viewer_pk = Membership.objects.get(workspace=self.workspace, user=self.viewer).pk

    def socket(self, client):
        name = settings.SESSION_COOKIE_NAME
        headers = [
            (b'origin', b'http://testserver'),
            (b'cookie', f'{name}={client.cookies[name].value}'.encode()),
        ]
        return WebsocketCommunicator(application, f'/ws/pages/{self.page.pk}/', headers=headers)

    def url(self, name, pk):
        return reverse(name, args=[self.workspace.pk, pk])

    async def test_removing_someone_closes_their_open_page(self):
        comm = self.socket(self.viewer_client)
        await comm.connect()
        await comm.receive_json_from(timeout=2)   # the "who is here" message
        await sync_to_async(self.owner_client.post)(self.url('member_remove', self.viewer_pk))
        output = await comm.receive_output(timeout=2)
        self.assertEqual(output['type'], 'websocket.close')
        self.assertEqual(output['code'], 4403)
        await comm.disconnect()

    async def test_leaving_closes_your_own_open_page(self):
        comm = self.socket(self.editor_client)
        await comm.connect()
        await comm.receive_json_from(timeout=2)
        await sync_to_async(self.editor_client.post)(self.url('member_remove', self.editor_pk))
        output = await comm.receive_output(timeout=2)
        self.assertEqual((output['type'], output['code']), ('websocket.close', 4403))
        await comm.disconnect()

    async def test_changing_a_role_tells_their_open_page_to_reload(self):
        comm = self.socket(self.editor_client)
        await comm.connect()
        await comm.receive_json_from(timeout=2)
        await sync_to_async(self.owner_client.post)(self.url('member_role', self.editor_pk), {'role': 'viewer'})
        message = await comm.receive_json_from(timeout=2)
        self.assertEqual(message, {'action': 'reload', 'page_id': self.page.pk})
        await comm.disconnect()

    async def test_setting_the_same_role_tells_nobody(self):
        comm = self.socket(self.editor_client)
        await comm.connect()
        await comm.receive_json_from(timeout=2)
        await sync_to_async(self.owner_client.post)(self.url('member_role', self.editor_pk), {'role': 'editor'})
        self.assertTrue(await comm.receive_nothing(timeout=0.3))
        await comm.disconnect()

    async def test_other_members_open_pages_are_untouched(self):
        owner = self.socket(self.owner_client)
        viewer = self.socket(self.viewer_client)
        await owner.connect()
        await viewer.connect()
        await owner.receive_json_from(timeout=2)   # owner alone
        await owner.receive_json_from(timeout=2)   # owner and viewer
        await viewer.receive_json_from(timeout=2)
        await sync_to_async(self.owner_client.post)(self.url('member_role', self.editor_pk), {'role': 'viewer'})
        self.assertTrue(await owner.receive_nothing(timeout=0.3))
        self.assertTrue(await viewer.receive_nothing(timeout=0.3))
        await owner.disconnect()
        await viewer.disconnect()
