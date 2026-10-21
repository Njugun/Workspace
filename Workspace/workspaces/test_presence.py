from channels.testing import WebsocketCommunicator
from django.conf import settings
from django.test import TransactionTestCase

from Workspace.asgi import application

from .consumers import _present
from .test_realtime import WorldMixin


class PresenceTests(WorldMixin, TransactionTestCase):
    def setUp(self):
        _present.clear()
        self.build_world()

    def socket(self, page_id, client):
        name = settings.SESSION_COOKIE_NAME
        headers = [
            (b'origin', b'http://testserver'),
            (b'cookie', f'{name}={client.cookies[name].value}'.encode()),
        ]
        return WebsocketCommunicator(application, f'/ws/pages/{page_id}/', headers=headers)

    def presence(self, users, page=None):
        return {'action': 'presence', 'page_id': (page or self.page).pk, 'users': users}

    async def test_connecting_announces_yourself(self):
        comm = self.socket(self.page.pk, self.owner_client)
        await comm.connect()
        self.assertEqual(await comm.receive_json_from(timeout=2), self.presence(['owner']))
        await comm.disconnect()

    async def test_everyone_on_the_page_hears_about_a_newcomer(self):
        first = self.socket(self.page.pk, self.owner_client)
        await first.connect()
        await first.receive_json_from(timeout=2)

        second = self.socket(self.page.pk, self.viewer_client)
        await second.connect()
        both = self.presence(['owner', 'viewer'])
        self.assertEqual(await first.receive_json_from(timeout=2), both)
        self.assertEqual(await second.receive_json_from(timeout=2), both)
        await first.disconnect()
        await second.disconnect()

    async def test_leaving_is_announced(self):
        first = self.socket(self.page.pk, self.owner_client)
        second = self.socket(self.page.pk, self.viewer_client)
        await first.connect()
        await second.connect()
        await first.receive_json_from(timeout=2)   # owner alone
        await first.receive_json_from(timeout=2)   # owner and viewer
        await second.disconnect()
        self.assertEqual(await first.receive_json_from(timeout=2), self.presence(['owner']))
        await first.disconnect()

    async def test_two_tabs_of_one_person_count_once(self):
        tab1 = self.socket(self.page.pk, self.owner_client)
        tab2 = self.socket(self.page.pk, self.owner_client)
        await tab1.connect()
        await tab2.connect()
        await tab1.receive_json_from(timeout=2)
        self.assertEqual(await tab1.receive_json_from(timeout=2), self.presence(['owner']))
        await tab1.disconnect()
        await tab2.disconnect()

    async def test_other_pages_are_not_told(self):
        elsewhere = self.socket(self.other_page.pk, self.owner_client)
        await elsewhere.connect()
        await elsewhere.receive_json_from(timeout=2)

        here = self.socket(self.page.pk, self.viewer_client)
        await here.connect()
        self.assertTrue(await elsewhere.receive_nothing(timeout=0.3))
        await here.disconnect()
        await elsewhere.disconnect()

    async def test_a_refused_connection_never_appears(self):
        refused = self.socket(self.page.pk, self.outsider_client)
        connected, _ = await refused.connect()
        self.assertFalse(connected)

        comm = self.socket(self.page.pk, self.owner_client)
        await comm.connect()
        self.assertEqual(await comm.receive_json_from(timeout=2), self.presence(['owner']))
        await comm.disconnect()

    async def test_the_list_is_cleaned_up_when_everyone_leaves(self):
        comm = self.socket(self.page.pk, self.owner_client)
        await comm.connect()
        await comm.receive_json_from(timeout=2)
        self.assertIn(self.page.pk, _present)
        await comm.disconnect()
        self.assertNotIn(self.page.pk, _present)
