from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase

from boats.models import BoatDetails, ParseJob, ParsedBoat
from boats.tasks import DETAIL_CACHE_LANGS, process_api_batch


class ApiModeNormalizationTaskTest(TestCase):
    def setUp(self):
        self.slug = 'jeanneau-sun-odyssey-440-bonbon'
        self.boat = ParsedBoat.objects.create(
            boat_id='boat-api-normalize-1',
            slug=self.slug,
            manufacturer='Jeanneau',
            model='Sun Odyssey 440',
            year=2022,
        )
        for lang in DETAIL_CACHE_LANGS:
            BoatDetails.objects.create(
                boat=self.boat,
                language=lang,
                extras=[],
                additional_services=[],
                delivery_extras=[],
                not_included=[],
                cockpit=[{'name': 'Legacy cockpit'}],
                entertainment=[{'name': 'Legacy entertainment'}],
                equipment=[{'name': 'Legacy equipment'}],
            )
            cache.set(
                f'boat_data:{self.slug}:{lang}',
                {
                    'slug': self.slug,
                    'name': 'Legacy Name',
                    'images': ['https://cdn.example.com/1.jpg'],
                    'extras': [],
                    'cockpit': [{'name': 'Legacy cockpit'}],
                    'entertainment': [{'name': 'Legacy entertainment'}],
                    'equipment': [{'name': 'Legacy equipment'}],
                },
                timeout=3600,
            )

        self.job = ParseJob.objects.create(
            mode='api',
            destination='turkey',
            total_slugs=1,
            total_batches=1,
            status='running',
        )

    @patch('boats.management.commands.parse_boats_parallel.Command._update_api_metadata', return_value=1)
    def test_process_api_batch_preserves_amenities_and_invalidates_detail_cache(self, _mock_update):
        api_meta_subset = {
            self.slug: {
                'country': 'Turkey',
                'region': 'Mugla',
                'city': 'Bodrum',
                'marina': 'Bodrum Milta Marina',
                'title': 'Jeanneau Sun Odyssey 440 | BonBon',
                'location': 'Mugla Province',
                'flag': 'TR',
                'coordinates': [],
                'category': 'sailing-yacht',
                'category_slug': 'sailing-yacht',
                'engine_type': '',
                'sail': '',
                'reviews_score': 0,
                'total_reviews': 0,
                'prepayment': 0,
                'newboat': False,
                'usp': [],
                'parameters': {},
                'charter_name': '',
                'charter_id': '',
                'charter_logo': '',
                'charter_rank': {},
            }
        }

        result = process_api_batch.run(
            str(self.job.job_id),
            [self.slug],
            api_meta_subset,
            {},
        )

        self.assertEqual(result.get('status'), 'ok')
        self.assertEqual(result.get('updated'), 1)

        # Amenities are HTML-owned — API mode must NOT touch them
        for details in BoatDetails.objects.filter(boat=self.boat):
            self.assertEqual(details.cockpit, [{'name': 'Legacy cockpit'}])
            self.assertEqual(details.entertainment, [{'name': 'Legacy entertainment'}])
            self.assertEqual(details.equipment, [{'name': 'Legacy equipment'}])

        for lang in DETAIL_CACHE_LANGS:
            self.assertIsNone(cache.get(f'boat_data:{self.slug}:{lang}'))

        self.job.refresh_from_db()
        self.assertEqual(self.job.processed, 1)
        self.assertEqual(self.job.success, 1)
        self.assertEqual(self.job.batches_done, 1)
