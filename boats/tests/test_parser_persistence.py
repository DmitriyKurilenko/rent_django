"""Tests for parser persistence behavior when source boat_id is missing."""
from unittest.mock import patch

from django.test import TestCase

from boats.models import ParsedBoat
from boats.parser import parse_boataround_url


def _lang_payload():
    langs = ['ru_RU', 'en_EN', 'de_DE', 'fr_FR', 'es_ES']
    payload = {}
    for lang in langs:
        payload[lang] = {
            'descriptions': {
                'title': 'Fountaine Pajot Lucia 40 | Merengue',
                'description': 'Test description',
                'location': 'Seychelles',
                'marina': 'Eden Island',
            },
            'amenities': {'cockpit': [], 'entertainment': [], 'equipment': []},
            'services': {
                'extras': [],
                'additional_services': [],
                'delivery_extras': [],
                'not_included': [],
            },
            '_fetch_ok': True,
        }
    return payload


class ParserPersistenceTest(TestCase):
    @patch('boats.parser._fetch_all_languages_data', return_value=_lang_payload())
    @patch('boats.parser._extract_not_included', return_value=[])
    @patch('boats.parser._extract_delivery_extras', return_value=[])
    @patch('boats.parser._extract_additional_services_from_component', return_value=[])
    @patch('boats.parser._extract_extras_from_component', return_value=[])
    @patch('boats.parser._extract_prices', return_value={})
    @patch('boats.parser._extract_boat_info')
    @patch('boats.parser.download_and_save_image')
    @patch('boats.parser.extract_pictures')
    @patch('boats.parser.fetch_page', return_value='<html><body>no id in html</body></html>')
    def test_persists_using_boatid_from_picture_path(
        self,
        _mock_fetch_page,
        mock_extract_pictures,
        mock_download_image,
        mock_boat_info,
        _mock_prices,
        _mock_extras,
        _mock_additional,
        _mock_delivery,
        _mock_not_included,
        _mock_all_lang_data,
    ):
        picture_boat_id = '62b96d157a9323583a5a4880'
        mock_extract_pictures.return_value = [f'boats/{picture_boat_id}/650d96fa43b7cac28800ead4.jpg']
        mock_download_image.return_value = f'https://cdn2.prvms.ru/yachts/{picture_boat_id}/650d96fa43b7cac28800ead4.jpg'
        mock_boat_info.return_value = {
            'title': 'Fountaine Pajot Lucia 40 | Merengue',
            'manufacturer': 'Fountaine Pajot',
            'model': 'Lucia 40',
            'year': '2021',
        }

        result = parse_boataround_url(
            'https://www.boataround.com/ru/yachta/fountaine-pajot-lucia-40-merengue/',
            save_to_db=True,
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.get('boat_id'), picture_boat_id)
        boat = ParsedBoat.objects.get(slug='fountaine-pajot-lucia-40-merengue')
        self.assertEqual(boat.boat_id, picture_boat_id)

    @patch('boats.parser._fetch_all_languages_data', return_value=_lang_payload())
    @patch('boats.parser._extract_not_included', return_value=[])
    @patch('boats.parser._extract_delivery_extras', return_value=[])
    @patch('boats.parser._extract_additional_services_from_component', return_value=[])
    @patch('boats.parser._extract_extras_from_component', return_value=[])
    @patch('boats.parser._extract_prices', return_value={})
    @patch('boats.parser._extract_boat_info')
    @patch('boats.parser.extract_pictures', return_value=[])
    @patch('boats.parser.fetch_page', return_value='<html><body>no id in html</body></html>')
    def test_persists_with_slug_fallback_boatid_when_source_id_missing(
        self,
        _mock_fetch_page,
        _mock_extract_pictures,
        mock_boat_info,
        _mock_prices,
        _mock_extras,
        _mock_additional,
        _mock_delivery,
        _mock_not_included,
        _mock_all_lang_data,
    ):
        slug = 'fountaine-pajot-lucia-40-merengue'
        mock_boat_info.return_value = {
            'title': 'Fountaine Pajot Lucia 40 | Merengue',
            'manufacturer': 'Fountaine Pajot',
            'model': 'Lucia 40',
            'year': '2021',
        }

        result = parse_boataround_url(
            f'https://www.boataround.com/ru/yachta/{slug}/',
            save_to_db=True,
        )

        self.assertIsNotNone(result)
        self.assertTrue(str(result.get('boat_id', '')).startswith('slug-'))
        boat = ParsedBoat.objects.get(slug=slug)
        self.assertTrue(boat.boat_id.startswith('slug-'))
