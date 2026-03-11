"""Tests for refresh amenities Celery task behavior on language fetch failures."""
from unittest.mock import patch

from django.test import TestCase

from boats.models import BoatDetails, ParsedBoat
from boats.tasks import refresh_boat_amenities


class RefreshAmenitiesTaskStatusTest(TestCase):
    def setUp(self):
        self.boat = ParsedBoat.objects.create(
            boat_id='boat-task-1',
            slug='lagoon-46-maryna',
            manufacturer='Lagoon',
            model='46',
            year=2023,
        )

    @patch('boats.parser._fetch_language_page_data')
    def test_task_returns_failed_when_all_language_pages_unavailable(self, mock_fetch_language):
        mock_fetch_language.return_value = {
            'descriptions': {'title': '', 'description': '', 'location': '', 'marina': ''},
            'services': {'extras': [], 'additional_services': [], 'delivery_extras': [], 'not_included': []},
            'amenities': {'cockpit': [], 'entertainment': [], 'equipment': []},
            '_fetch_ok': False,
        }

        result = refresh_boat_amenities.run(self.boat.slug)

        self.assertEqual(result.get('status'), 'failed')
        self.assertEqual(result.get('languages_updated'), 0)
        self.assertEqual(BoatDetails.objects.filter(boat=self.boat).count(), 0)

    @patch('boats.parser._fetch_language_page_data')
    def test_task_returns_partial_when_only_some_languages_loaded(self, mock_fetch_language):
        def _side_effect(slug, lang):
            if lang == 'ru_RU':
                return {
                    'descriptions': {'title': 'Test', 'description': '', 'location': '', 'marina': ''},
                    'services': {'extras': [], 'additional_services': [], 'delivery_extras': [], 'not_included': []},
                    'amenities': {'cockpit': [{'name': 'Shower'}], 'entertainment': [], 'equipment': []},
                    '_fetch_ok': True,
                }
            return {
                'descriptions': {'title': '', 'description': '', 'location': '', 'marina': ''},
                'services': {'extras': [], 'additional_services': [], 'delivery_extras': [], 'not_included': []},
                'amenities': {'cockpit': [], 'entertainment': [], 'equipment': []},
                '_fetch_ok': False,
            }

        mock_fetch_language.side_effect = _side_effect

        result = refresh_boat_amenities.run(self.boat.slug)

        self.assertEqual(result.get('status'), 'partial')
        self.assertEqual(result.get('languages_updated'), 1)
        self.assertEqual(BoatDetails.objects.filter(boat=self.boat).count(), 1)
        self.assertTrue(BoatDetails.objects.filter(boat=self.boat, language='ru_RU').exists())

