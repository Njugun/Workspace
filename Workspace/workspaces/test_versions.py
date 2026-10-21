from django.test import TestCase
from django.urls import reverse

from .test_realtime import WorldMixin


class BlockVersionTests(WorldMixin, TestCase):
    def setUp(self):
        self.build_world()
        self.url = reverse('block_update', args=[self.paragraph.pk])

    def save(self, client=None, **data):
        return (client or self.editor_client).post(self.url, data)

    def reload(self):
        self.paragraph.refresh_from_db()
        return self.paragraph

    def test_new_blocks_start_at_version_1(self):
        self.assertEqual(self.paragraph.version, 1)

    def test_saving_with_the_current_version_works_and_raises_it(self):
        response = self.save(text='New', version='1', original='Hello')
        self.assertEqual(response.status_code, 200)
        block = self.reload()
        self.assertEqual((block.text, block.version), ('New', 2))

    def test_saving_with_a_stale_version_is_refused(self):
        self.save(self.owner_client, text='Theirs', version='1', original='Hello')
        response = self.save(text='Mine', version='1', original='Hello')
        self.assertContains(response, 'Someone else changed')
        self.assertContains(response, 'Mine')       # their typing is kept in the box
        self.assertContains(response, 'Theirs')     # and the other version is shown
        self.assertContains(response, 'name="version" value="2"')   # a second save would be deliberate
        block = self.reload()
        self.assertEqual((block.text, block.version), ('Theirs', 2))

    def test_opening_and_leaving_without_edits_is_not_a_conflict(self):
        self.save(self.owner_client, text='Theirs', version='1', original='Hello')
        response = self.save(text='Hello', version='1', original='Hello')
        self.assertNotContains(response, 'Someone else changed')
        self.assertContains(response, 'Theirs')
        self.assertEqual(self.reload().text, 'Theirs')

    def test_saving_identical_text_changes_nothing(self):
        self.save(text='Hello', version='1')
        self.assertEqual(self.reload().version, 1)

    def test_save_mine_anyway_after_a_conflict_works(self):
        self.save(self.owner_client, text='Theirs', version='1', original='Hello')
        self.save(text='Mine', version='1', original='Hello')            # refused
        self.save(text='Mine', version='2', original='Theirs')           # the deliberate second save
        block = self.reload()
        self.assertEqual((block.text, block.version), ('Mine', 3))

    def test_a_save_without_a_version_still_works(self):
        self.save(text='Plain')
        block = self.reload()
        self.assertEqual((block.text, block.version), ('Plain', 2))

    def test_a_bad_version_is_rejected(self):
        self.assertEqual(self.save(text='X', version='abc').status_code, 400)

    def test_ticking_a_todo_does_not_cause_a_conflict(self):
        self.owner_client.post(reverse('block_toggle', args=[self.todo.pk]), {'checked': 'on'})
        self.editor_client.post(
            reverse('block_update', args=[self.todo.pk]),
            {'text': 'Task 2', 'version': '1', 'original': 'Task'},
        )
        self.todo.refresh_from_db()
        self.assertEqual(self.todo.text, 'Task 2')
