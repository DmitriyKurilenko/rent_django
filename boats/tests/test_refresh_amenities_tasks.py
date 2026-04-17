"""Tests for deprecated refresh amenities Celery tasks."""
from django.test import TestCase

from boats.models import BoatDetails, ParsedBoat
from boats.tasks import refresh_amenities_batch, refresh_boat_amenities


class RefreshAmenitiesTaskDeprecatedTest(TestCase):
    def setUp(self):
        self.boat = ParsedBoat.objects.create(
            boat_id='boat-task-1',
            slug='lagoon-46-maryna',
            manufacturer='Lagoon',
            model='46',
            year=2023,
        )

    def test_refresh_boat_amenities_returns_skipped(self):
        result = refresh_boat_amenities.run(self.boat.slug)

        self.assertEqual(result.get('status'), 'skipped')
        self.assertEqual(result.get('slug'), self.boat.slug)
        self.assertEqual(BoatDetails.objects.filter(boat=self.boat).count(), 0)

    def test_refresh_amenities_batch_reports_skipped(self):
        result = refresh_amenities_batch.run([self.boat.slug])

        self.assertEqual(result.get('status'), 'completed')
        self.assertEqual(result.get('total'), 1)
        self.assertEqual(result.get('skipped'), 1)
        self.assertEqual(result.get('success'), 0)
        self.assertEqual(result.get('failed'), 0)
        self.assertEqual(BoatDetails.objects.filter(boat=self.boat).count(), 0)
