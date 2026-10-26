from django.test import TestCase
from django.urls import reverse

from .models import Page
from .services import MAX_PAGE_DEPTH, create_page, create_workspace
from .test_realtime import WorldMixin


class SubPageTests(WorldMixin, TestCase):
    def setUp(self):
        self.build_world()
        self.url = reverse('subpage_create', args=[self.page.pk])

    def make(self, title, parent=None):
        return create_page(self.workspace, title, self.owner, parent=parent)

    # --- the sidebar ---

    def test_the_sidebar_nests_pages_under_their_parents(self):
        child = self.make('Child', parent=self.page)
        self.make('Grandchild', parent=child)
        response = self.owner_client.get(reverse('home'))
        workspace = next(ws for ws in response.context['sidebar_workspaces'] if ws.pk == self.workspace.pk)
        self.assertEqual(
            [(p.title, p.depth) for p in workspace.sidebar_pages],
            [('Main', 1), ('Child', 2), ('Grandchild', 3), ('Other', 1)],
        )

    def test_the_sidebar_fragment_lists_a_members_pages(self):
        response = self.editor_client.get(reverse('sidebar'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Main')
        self.assertContains(response, 'Other')
        self.assertNotContains(response, '<html')

    def test_the_sidebar_fragment_hides_other_workspaces_pages(self):
        elsewhere = create_workspace(self.outsider, 'Elsewhere')
        create_page(elsewhere, 'Secret plans', self.outsider)
        self.assertNotContains(self.editor_client.get(reverse('sidebar')), 'Secret plans')
        response = self.outsider_client.get(reverse('sidebar'))
        self.assertContains(response, 'Secret plans')
        self.assertNotContains(response, 'Main')

    def test_the_sidebar_fragment_needs_a_login(self):
        self.assertEqual(self.anonymous_client.get(reverse('sidebar')).status_code, 302)

    # --- creating sub-pages ---

    def test_an_editor_can_create_a_sub_page(self):
        response = self.editor_client.post(self.url, {'title': 'Sub'})
        page = Page.objects.get(title='Sub')
        self.assertEqual((page.parent, page.created_by), (self.page, self.editor))
        self.assertRedirects(response, reverse('page_detail', args=[page.pk]), fetch_redirect_response=False)

    def test_a_viewer_cannot_create_a_sub_page(self):
        response = self.viewer_client.post(self.url, {'title': 'Sub'})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Page.objects.filter(title='Sub').exists())

    def test_an_outsider_gets_a_404(self):
        self.assertEqual(self.outsider_client.get(self.url).status_code, 404)

    def test_the_depth_limit_shows_a_message(self):
        page = None
        for level in range(1, MAX_PAGE_DEPTH + 1):
            page = self.make(f'Level {level}', parent=page)
        response = self.editor_client.post(reverse('subpage_create', args=[page.pk]), {'title': 'Too deep'})
        self.assertContains(response, 'levels deep', status_code=400)
        self.assertFalse(Page.objects.filter(title='Too deep').exists())

    def test_an_empty_title_is_refused(self):
        response = self.editor_client.post(self.url, {'title': '   '})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Page.objects.filter(workspace=self.workspace).count(), 2)

    # --- on the page itself ---

    def test_a_sub_page_shows_its_ancestors(self):
        child = self.make('Child', parent=self.page)
        response = self.owner_client.get(reverse('page_detail', args=[child.pk]))
        self.assertEqual(response.context['ancestors'], [self.page])
        self.assertContains(response, 'id="breadcrumb"')

    def test_a_top_level_page_has_no_ancestors(self):
        response = self.owner_client.get(reverse('page_detail', args=[self.page.pk]))
        self.assertEqual(response.context['ancestors'], [])

    def test_the_sub_page_link_is_for_people_who_can_edit(self):
        self.assertContains(self.editor_client.get(reverse('page_detail', args=[self.page.pk])), self.url)
        self.assertNotContains(self.viewer_client.get(reverse('page_detail', args=[self.page.pk])), self.url)
