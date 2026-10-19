from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from .models import Block, Membership, Page, Workspace
from .services import create_workspace

User = get_user_model()
PASSWORD = 'S3cure-pass-phrase-77'


class WorkspaceTestCase(TestCase):
    """Shared data: one workspace with an owner, an editor and a viewer, plus an outsider."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user('owner', password=PASSWORD)
        cls.editor = User.objects.create_user('editor', password=PASSWORD)
        cls.viewer = User.objects.create_user('viewer', password=PASSWORD)
        cls.outsider = User.objects.create_user('outsider', password=PASSWORD)

        cls.workspace = create_workspace(cls.owner, 'Alpha Lab')
        Membership.objects.create(workspace=cls.workspace, user=cls.editor, role=Membership.Role.EDITOR)
        Membership.objects.create(workspace=cls.workspace, user=cls.viewer, role=Membership.Role.VIEWER)

        cls.page = Page.objects.create(workspace=cls.workspace, title='Plan', created_by=cls.owner)
        Block.objects.create(page=cls.page, kind=Block.Kind.PARAGRAPH, text='Hello team', position=2)
        Block.objects.create(page=cls.page, kind=Block.Kind.HEADING, text='Goals', position=1)
        Block.objects.create(page=cls.page, kind=Block.Kind.TODO, text='Invite people', position=1.5)

        cls.page_url = reverse('page_detail', args=[cls.page.pk])
        cls.new_page_url = reverse('page_create', args=[cls.workspace.pk])


class PageAccessTests(WorkspaceTestCase):
    def test_anonymous_user_is_sent_to_login(self):
        response = self.client.get(self.page_url)
        self.assertRedirects(
            response, f"{reverse('login')}?next={self.page_url}", fetch_redirect_response=False
        )

    def test_every_member_can_open_the_page(self):
        for user in (self.owner, self.editor, self.viewer):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                response = self.client.get(self.page_url)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'Hello team')

    def test_outsider_gets_404(self):
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(self.page_url).status_code, 404)

    def test_missing_page_gets_the_same_404(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse('page_detail', args=[99999]))
        self.assertEqual(response.status_code, 404)

    def test_blocks_come_out_in_position_order(self):
        positions = list(self.page.blocks.values_list('position', flat=True))
        self.assertEqual(positions, [1.0, 1.5, 2.0])


class PageCreateTests(WorkspaceTestCase):
    def test_owner_and_editor_can_open_the_form(self):
        for user in (self.owner, self.editor):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                self.assertEqual(self.client.get(self.new_page_url).status_code, 200)

    def test_viewer_is_forbidden(self):
        self.client.force_login(self.viewer)
        self.assertEqual(self.client.get(self.new_page_url).status_code, 403)

    def test_viewer_cannot_create_a_page_by_posting(self):
        self.client.force_login(self.viewer)
        response = self.client.post(self.new_page_url, {'title': 'Sneaky'})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Page.objects.filter(title='Sneaky').exists())

    def test_outsider_gets_404(self):
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(self.new_page_url).status_code, 404)

    def test_editor_can_create_a_page(self):
        self.client.force_login(self.editor)
        response = self.client.post(self.new_page_url, {'title': 'Roadmap'})
        page = Page.objects.get(title='Roadmap')
        self.assertRedirects(response, reverse('page_detail', args=[page.pk]))
        self.assertEqual(page.workspace, self.workspace)
        self.assertEqual(page.created_by, self.editor)


class WorkspaceTests(WorkspaceTestCase):
    def test_creator_becomes_owner(self):
        membership = Membership.objects.get(workspace=self.workspace, user=self.owner)
        self.assertEqual(membership.role, Membership.Role.OWNER)

    def test_signup_creates_a_workspace_owned_by_the_new_user(self):
        response = self.client.post(reverse('signup'), {
            'username': 'newbie', 'password1': PASSWORD, 'password2': PASSWORD,
        })
        self.assertEqual(response.status_code, 302)
        workspace = Workspace.objects.get(name="newbie's Workspace")
        membership = workspace.memberships.get()
        self.assertEqual(membership.user.username, 'newbie')
        self.assertEqual(membership.role, Membership.Role.OWNER)

    def test_sidebar_lists_only_my_workspaces(self):
        self.client.force_login(self.owner)
        self.assertContains(self.client.get(reverse('home')), 'Alpha Lab')
        self.client.force_login(self.outsider)
        self.assertNotContains(self.client.get(reverse('home')), 'Alpha Lab')

    def test_a_user_cannot_join_the_same_workspace_twice(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Membership.objects.create(
                workspace=self.workspace, user=self.editor, role=Membership.Role.VIEWER
            )