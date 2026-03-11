"""Tests for refresh_amenities management command."""
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase

from boats.management.commands.refresh_amenities import Command
from boats.models import ParsedBoat


class RefreshAmenitiesDestinationSelectionTest(TestCase):
    def setUp(self):
        ParsedBoat.objects.create(boat_id='boat-1', slug='boat-a')
        ParsedBoat.objects.create(boat_id='boat-2', slug='boat-b')
        self.command = Command()

    @patch('boats.boataround_api.BoataroundAPI.search')
    def test_get_slugs_by_destination_filters_existing_and_deduplicates(self, mock_search):
        mock_search.side_effect = [
            {
                'boats': [{'slug': 'boat-a'}] * 10 + [{'slug': 'missing-slug'}] * 8,
                'total': 36,
            },
            {
                'boats': [{'slug': 'boat-b'}],
                'total': 36,
            },
        ]

        slugs = self.command._get_slugs_by_destination('seychelles')

        self.assertEqual(slugs, ['boat-a', 'boat-b'])

    @patch('boats.boataround_api.BoataroundAPI.search')
    def test_get_slugs_by_destination_applies_limit_after_deduplicate(self, mock_search):
        mock_search.return_value = {
            'boats': [{'slug': 'boat-a'}] * 5 + [{'slug': 'boat-b'}] * 5,
            'total': 10,
        }

        slugs = self.command._get_slugs_by_destination('seychelles', limit=1)

        self.assertEqual(slugs, ['boat-a'])


class RefreshAmenitiesAsyncCommandTest(SimpleTestCase):
    def setUp(self):
        self.command = Command()

    @patch('boats.tasks.refresh_amenities_batch.delay')
    def test_run_async_continues_when_no_active_workers_detected(self, mock_delay):
        mock_delay.return_value = SimpleNamespace(id='task-1')

        with patch.object(self.command, '_get_active_workers', return_value={}):
            self.command._run_async(
                slugs=['boat-a'],
                batch_size=1,
                wait_for_completion=False,
            )

        self.assertEqual(mock_delay.call_count, 1)

    @patch('boats.tasks.refresh_amenities_batch.delay')
    def test_run_async_waits_and_aggregates_results(self, mock_delay):
        mock_delay.side_effect = [
            SimpleNamespace(id='task-1'),
            SimpleNamespace(id='task-2'),
        ]
        expected_summary = {
            'total_batches': 2,
            'completed_batches': 2,
            'failed_batches': 0,
            'success_boats': 2,
            'failed_boats': 0,
            'timed_out_batches': 0,
            'pending_task_ids': [],
        }

        with patch.object(self.command, '_get_active_workers', return_value={'celery@worker': {'ok': 'pong'}}):
            with patch.object(self.command, '_wait_for_async_batches', return_value=expected_summary) as mock_wait:
                self.command._run_async(
                    slugs=['boat-a', 'boat-b'],
                    batch_size=1,
                    wait_for_completion=True,
                    wait_timeout=30,
                    poll_interval=1,
                )

        mock_wait.assert_called_once_with(
            task_ids=['task-1', 'task-2'],
            timeout=30,
            poll_interval=1,
        )

    @patch('celery.result.AsyncResult')
    def test_wait_for_async_batches_collects_summary(self, mock_async_result):
        result_map = {
            'task-ok': SimpleNamespace(
                state='SUCCESS',
                successful=lambda: True,
                result={'success': 3, 'failed': 1},
            ),
            'task-fail': SimpleNamespace(
                state='FAILURE',
                successful=lambda: False,
                result='boom',
            ),
        }

        def _fake_async_result(task_id):
            return result_map[task_id]

        mock_async_result.side_effect = _fake_async_result

        summary = self.command._wait_for_async_batches(
            task_ids=['task-ok', 'task-fail'],
            timeout=5,
            poll_interval=0,
        )

        self.assertEqual(summary['total_batches'], 2)
        self.assertEqual(summary['completed_batches'], 2)
        self.assertEqual(summary['failed_batches'], 1)
        self.assertEqual(summary['success_boats'], 3)
        self.assertEqual(summary['failed_boats'], 1)
        self.assertEqual(summary['timed_out_batches'], 0)
