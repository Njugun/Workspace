from django.test import TestCase

from .models import Membership
from .services import MembershipError, add_member, change_role, remove_member
from .test_realtime import WorldMixin


class MemberRulesTests(WorldMixin, TestCase):
    """The world has one owner, an editor, a viewer, and an outsider who is not a member."""

    def setUp(self):
        self.build_world()

    def membership(self, user):
        return Membership.objects.get(workspace=self.workspace, user=user)

    # --- adding ---

    def test_add_member_by_username(self):
        membership = add_member(self.workspace, 'outsider', 'viewer')
        self.assertEqual((membership.user, membership.role), (self.outsider, 'viewer'))

    def test_username_match_ignores_case_and_spaces(self):
        add_member(self.workspace, '  OutSider ', 'editor')
        self.assertEqual(self.membership(self.outsider).role, 'editor')

    def test_unknown_username_is_refused(self):
        with self.assertRaises(MembershipError):
            add_member(self.workspace, 'nobody', 'viewer')

    def test_existing_member_cannot_be_added_again(self):
        with self.assertRaises(MembershipError):
            add_member(self.workspace, 'viewer', 'editor')
        self.assertEqual(self.membership(self.viewer).role, 'viewer')

    def test_unknown_role_is_refused_when_adding(self):
        with self.assertRaises(MembershipError):
            add_member(self.workspace, 'outsider', 'admin')
        self.assertFalse(Membership.objects.filter(workspace=self.workspace, user=self.outsider).exists())

    # --- changing roles ---

    def test_viewer_can_be_promoted_to_owner(self):
        change_role(self.membership(self.viewer), 'owner')
        self.assertEqual(self.membership(self.viewer).role, 'owner')

    def test_editor_can_be_demoted_to_viewer(self):
        change_role(self.membership(self.editor), 'viewer')
        self.assertEqual(self.membership(self.editor).role, 'viewer')

    def test_the_last_owner_cannot_be_demoted(self):
        with self.assertRaises(MembershipError):
            change_role(self.membership(self.owner), 'editor')
        self.assertEqual(self.membership(self.owner).role, 'owner')

    def test_an_owner_can_be_demoted_when_another_owner_exists(self):
        change_role(self.membership(self.editor), 'owner')
        change_role(self.membership(self.owner), 'editor')
        self.assertEqual(self.membership(self.owner).role, 'editor')

    def test_unknown_role_is_refused_when_changing(self):
        with self.assertRaises(MembershipError):
            change_role(self.membership(self.editor), 'admin')
        self.assertEqual(self.membership(self.editor).role, 'editor')

    def test_setting_the_same_role_is_fine(self):
        change_role(self.membership(self.owner), 'owner')
        self.assertEqual(self.membership(self.owner).role, 'owner')

    # --- removing ---

    def test_a_member_can_be_removed(self):
        remove_member(self.membership(self.viewer))
        self.assertFalse(Membership.objects.filter(workspace=self.workspace, user=self.viewer).exists())

    def test_the_last_owner_cannot_be_removed(self):
        with self.assertRaises(MembershipError):
            remove_member(self.membership(self.owner))
        self.assertTrue(Membership.objects.filter(workspace=self.workspace, user=self.owner).exists())

    def test_an_owner_can_be_removed_when_another_owner_exists(self):
        change_role(self.membership(self.editor), 'owner')
        remove_member(self.membership(self.owner))
        self.assertFalse(Membership.objects.filter(workspace=self.workspace, user=self.owner).exists())

    def test_removing_one_member_leaves_the_others(self):
        remove_member(self.membership(self.viewer))
        self.assertEqual(self.workspace.memberships.count(), 2)
