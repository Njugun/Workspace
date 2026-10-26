from django.test import TestCase
from django.urls import reverse

from .models import Block, Page
from .services import create_page
from .test_realtime import WorldMixin


class RenameAndDeleteTests(WorldMixin, TestCase):
    def setUp(self):
        self.build_world()
        self.detail = reverse('page_detail', args=[self.page.pk])
        self.edit_url = reverse('page_title_edit', args=[self.page.pk])
        self.rename_url = reverse('page_rename', args=[self.page.pk])
        self.delete_url = reverse('page_delete', args=[self.page.pk])

    def nest(self):
        """Gives Main a child page with one block."""
        child = create_page(self.workspace, 'Child', self.owner, parent=self.page)
        Block.objects.create(page=child, kind=Block.Kind.PARAGRAPH, text='x', position=1.0)
        return child

    # --- renaming ---

    def test_an_editor_gets_the_rename_form(self):
        response = self.editor_client.get(self.edit_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="title"')

    def test_a_viewer_cannot_get_the_rename_form(self):
        self.assertEqual(self.viewer_client.get(self.edit_url).status_code, 403)

    def test_an_outsider_cannot_get_the_rename_form(self):
        self.assertEqual(self.outsider_client.get(self.edit_url).status_code, 404)

    def test_an_editor_can_rename_a_page(self):
        response = self.editor_client.post(self.rename_url, {'title': 'Plan'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Plan')
        self.page.refresh_from_db()
        self.assertEqual(self.page.title, 'Plan')

    def test_a_viewer_cannot_rename_a_page(self):
        response = self.viewer_client.post(self.rename_url, {'title': 'Plan'})
        self.assertEqual(response.status_code, 403)
        self.page.refresh_from_db()
        self.assertEqual(self.page.title, 'Main')

    def test_a_blank_title_keeps_the_old_one(self):
        response = self.editor_client.post(self.rename_url, {'title': '   '})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Main')
        self.page.refresh_from_db()
        self.assertEqual(self.page.title, 'Main')

    def test_editors_can_click_the_title_to_rename(self):
        self.assertContains(self.editor_client.get(self.detail), self.edit_url)

    def test_viewers_cannot_click_the_title_to_rename(self):
        self.assertNotContains(self.viewer_client.get(self.detail), self.edit_url)

    # --- deleting ---

    def test_only_owners_see_the_delete_link(self):
        self.assertContains(self.owner_client.get(self.detail), self.delete_url)
        self.assertNotContains(self.editor_client.get(self.detail), self.delete_url)

    def test_the_confirmation_says_what_would_go(self):
        self.nest()
        response = self.owner_client.get(self.delete_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '2 pages')
        self.assertContains(response, '4 blocks')
        self.assertTrue(Page.objects.filter(pk=self.page.pk).exists())

    def test_an_editor_cannot_delete_a_page(self):
        self.assertEqual(self.editor_client.get(self.delete_url).status_code, 403)
        self.assertEqual(self.editor_client.post(self.delete_url).status_code, 403)
        self.assertTrue(Page.objects.filter(pk=self.page.pk).exists())

    def test_an_outsider_cannot_reach_the_delete_page(self):
        self.assertEqual(self.outsider_client.get(self.delete_url).status_code, 404)

    def test_an_owner_deletes_a_top_level_page_and_goes_home(self):
        pk = self.page.pk
        response = self.owner_client.post(self.delete_url)
        self.assertRedirects(response, reverse('home'), fetch_redirect_response=False)
        self.assertFalse(Page.objects.filter(pk=pk).exists())
        self.assertFalse(Block.objects.filter(page_id=pk).exists())

    def test_deleting_a_sub_page_returns_to_its_parent(self):
        child = self.nest()
        response = self.owner_client.post(reverse('page_delete', args=[child.pk]))
        self.assertRedirects(response, self.detail, fetch_redirect_response=False)
        self.assertTrue(Page.objects.filter(pk=self.page.pk).exists())

    def test_deleting_a_page_deletes_its_sub_pages(self):
        child = self.nest()
        self.owner_client.post(self.delete_url)
        self.assertFalse(Page.objects.filter(pk=child.pk).exists())
