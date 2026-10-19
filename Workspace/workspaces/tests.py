from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Block, Membership, Page, Workspace
from .services import create_workspace

User = get_user_model()
PASSWORD = 'S3cure-pass-phrase-77'


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
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


class BlockToggleTests(WorkspaceTestCase):
    def setUp(self):
        self.todo = Block.objects.get(page=self.page, kind=Block.Kind.TODO)
        self.url = reverse('block_toggle', args=[self.todo.pk])

    def test_editor_can_tick_and_untick(self):
        self.client.force_login(self.editor)
        response = self.client.post(self.url, {'checked': 'on'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'line-through')
        self.todo.refresh_from_db()
        self.assertTrue(self.todo.checked)

        self.client.post(self.url)  # an unticked checkbox sends nothing
        self.todo.refresh_from_db()
        self.assertFalse(self.todo.checked)

    def test_viewer_cannot_tick(self):
        self.client.force_login(self.viewer)
        response = self.client.post(self.url, {'checked': 'on'})
        self.assertEqual(response.status_code, 403)
        self.todo.refresh_from_db()
        self.assertFalse(self.todo.checked)

    def test_outsider_gets_404(self):
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.post(self.url, {'checked': 'on'}).status_code, 404)

    def test_get_is_not_allowed(self):
        self.client.force_login(self.editor)
        self.assertEqual(self.client.get(self.url).status_code, 405)

    def test_only_todo_blocks_can_be_ticked(self):
        heading = Block.objects.get(page=self.page, kind=Block.Kind.HEADING)
        self.client.force_login(self.editor)
        url = reverse('block_toggle', args=[heading.pk])
        self.assertEqual(self.client.post(url, {'checked': 'on'}).status_code, 400)


class BlockToggleTests(WorkspaceTestCase):
    def setUp(self):
        self.todo = Block.objects.get(page=self.page, kind=Block.Kind.TODO)
        self.url = reverse('block_toggle', args=[self.todo.pk])

    def test_editor_can_tick_and_untick(self):
        self.client.force_login(self.editor)
        response = self.client.post(self.url, {'checked': 'on'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'line-through')
        self.todo.refresh_from_db()
        self.assertTrue(self.todo.checked)

        self.client.post(self.url)  # an unticked checkbox sends nothing
        self.todo.refresh_from_db()
        self.assertFalse(self.todo.checked)

    def test_viewer_cannot_tick(self):
        self.client.force_login(self.viewer)
        response = self.client.post(self.url, {'checked': 'on'})
        self.assertEqual(response.status_code, 403)
        self.todo.refresh_from_db()
        self.assertFalse(self.todo.checked)

    def test_outsider_gets_404(self):
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.post(self.url, {'checked': 'on'}).status_code, 404)

    def test_get_is_not_allowed(self):
        self.client.force_login(self.editor)
        self.assertEqual(self.client.get(self.url).status_code, 405)

    def test_only_todo_blocks_can_be_ticked(self):
        heading = Block.objects.get(page=self.page, kind=Block.Kind.HEADING)
        self.client.force_login(self.editor)
        url = reverse('block_toggle', args=[heading.pk])
        self.assertEqual(self.client.post(url, {'checked': 'on'}).status_code, 400)


class BlockEditTests(WorkspaceTestCase):
    def setUp(self):
        self.block = Block.objects.get(page=self.page, kind=Block.Kind.PARAGRAPH)
        self.edit_url = reverse('block_edit', args=[self.block.pk])
        self.update_url = reverse('block_update', args=[self.block.pk])

    def test_editor_gets_the_edit_form(self):
        self.client.force_login(self.editor)
        response = self.client.get(self.edit_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="Hello team"')

    def test_editor_can_change_the_text(self):
        self.client.force_login(self.editor)
        response = self.client.post(self.update_url, {'text': '  New words  '})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'New words')
        self.block.refresh_from_db()
        self.assertEqual(self.block.text, 'New words')

    def test_viewer_cannot_edit(self):
        self.client.force_login(self.viewer)
        self.assertEqual(self.client.get(self.edit_url).status_code, 403)
        response = self.client.post(self.update_url, {'text': 'Hacked'})
        self.assertEqual(response.status_code, 403)
        self.block.refresh_from_db()
        self.assertEqual(self.block.text, 'Hello team')

    def test_outsider_gets_404(self):
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(self.edit_url).status_code, 404)
        self.assertEqual(self.client.post(self.update_url, {'text': 'x'}).status_code, 404)

    def test_html_in_text_is_escaped(self):
        self.client.force_login(self.editor)
        response = self.client.post(self.update_url, {'text': '<script>alert(1)</script>'})
        self.assertNotContains(response, '<script>')
        self.assertContains(response, '&lt;script&gt;')




class BlockCreateDeleteTests(WorkspaceTestCase):
    def setUp(self):
        self.create_url = reverse('block_create', args=[self.page.pk])
        self.paragraph = Block.objects.get(page=self.page, kind=Block.Kind.PARAGRAPH)
        self.delete_url = reverse('block_delete', args=[self.paragraph.pk])

    def test_editor_can_add_each_kind_at_the_end(self):
        self.client.force_login(self.editor)
        for kind in Block.Kind.values:
            with self.subTest(kind=kind):
                self.assertEqual(self.client.post(self.create_url, {'kind': kind}).status_code, 200)
        positions = list(self.page.blocks.values_list('position', flat=True))
        self.assertEqual(positions, [1.0, 1.5, 2.0, 3.0, 4.0, 5.0])

    def test_first_block_on_an_empty_page_starts_at_one(self):
        empty = Page.objects.create(workspace=self.workspace, title='Empty')
        self.client.force_login(self.owner)
        self.client.post(reverse('block_create', args=[empty.pk]), {'kind': 'paragraph'})
        self.assertEqual(empty.blocks.get().position, 1.0)

    def test_unknown_kind_is_rejected(self):
        self.client.force_login(self.editor)
        before = Block.objects.count()
        self.assertEqual(self.client.post(self.create_url, {'kind': 'video'}).status_code, 400)
        self.assertEqual(Block.objects.count(), before)

    def test_viewer_cannot_add(self):
        self.client.force_login(self.viewer)
        before = Block.objects.count()
        self.assertEqual(self.client.post(self.create_url, {'kind': 'paragraph'}).status_code, 403)
        self.assertEqual(Block.objects.count(), before)

    def test_outsider_cannot_add(self):
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.post(self.create_url, {'kind': 'paragraph'}).status_code, 404)

    def test_editor_can_delete(self):
        self.client.force_login(self.editor)
        response = self.client.post(self.delete_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b'')
        self.assertFalse(Block.objects.filter(pk=self.paragraph.pk).exists())

    def test_viewer_cannot_delete(self):
        self.client.force_login(self.viewer)
        self.assertEqual(self.client.post(self.delete_url).status_code, 403)
        self.assertTrue(Block.objects.filter(pk=self.paragraph.pk).exists())

    def test_outsider_cannot_delete(self):
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.post(self.delete_url).status_code, 404)
        self.assertTrue(Block.objects.filter(pk=self.paragraph.pk).exists())

    def test_delete_needs_post(self):
        self.client.force_login(self.editor)
        self.assertEqual(self.client.get(self.delete_url).status_code, 405)

    def test_editor_sees_editing_controls(self):
        self.client.force_login(self.editor)
        response = self.client.get(self.page_url)
        self.assertContains(response, self.create_url)
        self.assertContains(response, self.delete_url)

    def test_viewer_sees_no_editing_controls(self):
        self.client.force_login(self.viewer)
        response = self.client.get(self.page_url)
        self.assertNotContains(response, self.create_url)
        self.assertNotContains(response, '/delete/')