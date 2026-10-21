from django.test import TestCase
from django.urls import reverse

from .models import Membership
from .services import create_workspace
from .test_realtime import WorldMixin


class MembersPageTests(WorldMixin, TestCase):
    def setUp(self):
        self.build_world()

    def membership(self, user):
        return Membership.objects.get(workspace=self.workspace, user=user)

    def url(self, name, *extra):
        return reverse(name, args=[self.workspace.pk, *extra])

    # --- looking at the page ---

    def test_owner_sees_the_list_and_the_add_form(self):
        response = self.owner_client.get(self.url('members'))
        self.assertEqual(response.status_code, 200)
        for name in ('owner', 'editor', 'viewer'):
            self.assertContains(response, name)
        self.assertContains(response, 'Add someone')

    def test_editor_sees_the_list_without_the_add_form(self):
        response = self.editor_client.get(self.url('members'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'viewer')
        self.assertNotContains(response, 'Add someone')

    def test_outsider_gets_a_404(self):
        self.assertEqual(self.outsider_client.get(self.url('members')).status_code, 404)

    def test_anonymous_user_is_sent_to_log_in(self):
        self.assertEqual(self.anonymous_client.get(self.url('members')).status_code, 302)

    # --- adding ---

    def test_owner_can_add_someone(self):
        response = self.owner_client.post(self.url('member_add'), {'username': 'outsider', 'role': 'viewer'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.membership(self.outsider).role, 'viewer')

    def test_editor_cannot_add_anyone(self):
        response = self.editor_client.post(self.url('member_add'), {'username': 'outsider', 'role': 'viewer'})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Membership.objects.filter(workspace=self.workspace, user=self.outsider).exists())

    def test_unknown_username_shows_a_message(self):
        response = self.owner_client.post(self.url('member_add'), {'username': 'nobody', 'role': 'viewer'})
        self.assertContains(response, 'no account', status_code=400)

    def test_non_member_cannot_add_anyone_either(self):
        response = self.outsider_client.post(self.url('member_add'), {'username': 'outsider', 'role': 'owner'})
        self.assertEqual(response.status_code, 404)
        self.assertFalse(Membership.objects.filter(workspace=self.workspace, user=self.outsider).exists())

    # --- changing roles ---

    def test_owner_can_change_a_role(self):
        response = self.owner_client.post(self.url('member_role', self.membership(self.editor).pk), {'role': 'viewer'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.membership(self.editor).role, 'viewer')

    def test_editor_cannot_change_a_role(self):
        response = self.editor_client.post(self.url('member_role', self.membership(self.viewer).pk), {'role': 'owner'})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.membership(self.viewer).role, 'viewer')

    def test_last_owner_cannot_demote_themselves(self):
        response = self.owner_client.post(self.url('member_role', self.membership(self.owner).pk), {'role': 'editor'})
        self.assertContains(response, 'at least one owner', status_code=400)
        self.assertEqual(self.membership(self.owner).role, 'owner')

    # --- removing and leaving ---

    def test_owner_can_remove_someone(self):
        response = self.owner_client.post(self.url('member_remove', self.membership(self.viewer).pk))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Membership.objects.filter(workspace=self.workspace, user=self.viewer).exists())

    def test_editor_cannot_remove_someone_else(self):
        response = self.editor_client.post(self.url('member_remove', self.membership(self.viewer).pk))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Membership.objects.filter(workspace=self.workspace, user=self.viewer).exists())

    def test_a_member_can_leave(self):
        response = self.editor_client.post(self.url('member_remove', self.membership(self.editor).pk))
        self.assertRedirects(response, reverse('home'), fetch_redirect_response=False)
        self.assertFalse(Membership.objects.filter(workspace=self.workspace, user=self.editor).exists())

    def test_the_last_owner_cannot_leave(self):
        response = self.owner_client.post(self.url('member_remove', self.membership(self.owner).pk))
        self.assertContains(response, 'at least one owner', status_code=400)
        self.assertTrue(Membership.objects.filter(workspace=self.workspace, user=self.owner).exists())

    def test_an_owner_cannot_reach_another_workspaces_members(self):
        other = create_workspace(self.outsider, 'Other')
        other_owner = Membership.objects.get(workspace=other, user=self.outsider)
        response = self.owner_client.post(self.url('member_role', other_owner.pk), {'role': 'viewer'})
        self.assertEqual(response.status_code, 404)
        other_owner.refresh_from_db()
        self.assertEqual(other_owner.role, 'owner')
