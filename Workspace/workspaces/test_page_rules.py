from django.test import TestCase

from .models import Block, Page
from .services import (
    MAX_PAGE_DEPTH,
    PageError,
    create_page,
    create_workspace,
    delete_page,
    deletion_summary,
    descendant_ids,
    rename_page,
)
from .test_realtime import WorldMixin


class PageRulesTests(WorldMixin, TestCase):
    """The world has two top-level pages, Main (with three blocks) and Other."""

    def setUp(self):
        self.build_world()

    def make(self, title, parent=None):
        return create_page(self.workspace, title, self.owner, parent=parent)

    def nest(self):
        """Gives Main a child page (with one block) and a grandchild."""
        child = self.make('Child', parent=self.page)
        grandchild = self.make('Grandchild', parent=child)
        Block.objects.create(page=child, kind=Block.Kind.PARAGRAPH, text='x', position=1.0)
        return child, grandchild

    # --- creating ---

    def test_a_top_level_page_is_created(self):
        page = self.make('Notes')
        self.assertEqual((page.title, page.parent, page.created_by, page.workspace), ('Notes', None, self.owner, self.workspace))

    def test_a_sub_page_knows_its_parent(self):
        page = self.make('Notes', parent=self.page)
        self.assertEqual(page.parent, self.page)

    def test_the_title_is_trimmed(self):
        self.assertEqual(self.make('  Notes  ').title, 'Notes')

    def test_an_empty_title_is_refused(self):
        for title in ('', '   ', None):
            with self.assertRaises(PageError):
                self.make(title)
        self.assertEqual(Page.objects.filter(workspace=self.workspace).count(), 2)

    def test_a_parent_in_another_workspace_is_refused(self):
        elsewhere = create_workspace(self.outsider, 'Elsewhere')
        foreign = create_page(elsewhere, 'Foreign', self.outsider)
        with self.assertRaises(PageError):
            self.make('Child', parent=foreign)

    def test_nesting_stops_at_the_depth_limit(self):
        page = None
        for level in range(1, MAX_PAGE_DEPTH + 1):
            page = self.make(f'Level {level}', parent=page)
        with self.assertRaises(PageError):
            self.make('Too deep', parent=page)

    # --- renaming ---

    def test_a_page_can_be_renamed(self):
        rename_page(self.page, '  Plan  ')
        self.page.refresh_from_db()
        self.assertEqual(self.page.title, 'Plan')

    def test_renaming_to_nothing_is_refused(self):
        with self.assertRaises(PageError):
            rename_page(self.page, '   ')
        self.page.refresh_from_db()
        self.assertEqual(self.page.title, 'Main')

    def test_a_very_long_title_is_refused(self):
        with self.assertRaises(PageError):
            rename_page(self.page, 'x' * 201)
        self.page.refresh_from_db()
        self.assertEqual(self.page.title, 'Main')

    # --- deleting ---

    def test_descendants_include_every_level(self):
        child, grandchild = self.nest()
        self.assertCountEqual(descendant_ids(self.page), [child.pk, grandchild.pk])

    def test_the_summary_counts_pages_and_blocks_inside(self):
        self.nest()
        self.assertEqual(deletion_summary(self.page), (3, 4))

    def test_deleting_a_page_removes_its_blocks_and_sub_pages(self):
        child, grandchild = self.nest()
        expected = [self.page.pk, child.pk, grandchild.pk]   # read first: deleting clears the ids
        removed = delete_page(self.page)
        self.assertCountEqual(removed, expected)
        self.assertFalse(Page.objects.filter(pk__in=removed).exists())
        self.assertFalse(Block.objects.filter(page_id__in=removed).exists())

    def test_other_pages_are_untouched_by_a_deletion(self):
        self.nest()
        delete_page(self.page)
        self.assertTrue(Page.objects.filter(pk=self.other_page.pk).exists())

    def test_deleting_a_sub_page_leaves_its_parent_alone(self):
        child, grandchild = self.nest()
        expected = [child.pk, grandchild.pk]
        removed = delete_page(child)
        self.assertCountEqual(removed, expected)
        self.assertTrue(Page.objects.filter(pk=self.page.pk).exists())
        self.assertEqual(self.page.blocks.count(), 3)