import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase

from boats.management.commands.parse_boats_parallel import Command


class ParseBoatsParallelCacheTest(SimpleTestCase):
    def setUp(self):
        self.command = Command()
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.cache_dir = Path(self.tmp_dir.name)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_save_and_load_cache_with_api_meta(self):
        slugs = ['boat-a', 'boat-b']
        thumb_map = {'boat-a': 'https://img/a.jpg'}
        api_meta = {
            'boat-a': {
                'country': 'Turkey',
                'region': 'Mugla',
                'city': 'Fethiye',
                'engine_type': 'inboard',
            }
        }
        api_meta_by_lang = {
            'ru_RU': {
                'boat-a': {
                    'country': 'Турция',
                    'region': 'Мугла',
                    'city': 'Фетхие',
                }
            }
        }

        with patch('boats.management.commands.parse_boats_parallel.CACHE_DIR', self.cache_dir):
            self.command._save_cache('turkey', 1, slugs, thumb_map, api_meta, api_meta_by_lang)
            loaded = self.command._load_cache('turkey', cache_ttl=24, max_pages=1)

        self.assertIsNotNone(loaded)
        self.assertEqual(loaded['slugs'], slugs)
        self.assertEqual(loaded['thumb_map'], thumb_map)
        self.assertEqual(loaded['api_meta'], api_meta)
        self.assertEqual(loaded['api_meta_by_lang'], api_meta_by_lang)

    def test_load_legacy_list_cache_format(self):
        legacy_path = self.cache_dir / 'turkey_mp1.json'
        legacy_path.write_text(json.dumps(['legacy-a', 'legacy-b']))

        with patch('boats.management.commands.parse_boats_parallel.CACHE_DIR', self.cache_dir):
            loaded = self.command._load_cache('turkey', cache_ttl=24, max_pages=1)

        self.assertIsNotNone(loaded)
        self.assertEqual(loaded['slugs'], ['legacy-a', 'legacy-b'])
        self.assertEqual(loaded['thumb_map'], {})
        self.assertEqual(loaded['api_meta'], {})
        self.assertEqual(loaded['api_meta_by_lang'], {})
