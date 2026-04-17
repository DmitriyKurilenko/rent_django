"""Tests for parser persistence behavior when source boat_id is missing."""
from unittest.mock import patch

from django.test import TestCase

from boats.models import BoatDescription, BoatDetails, ParsedBoat
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


def _lang_payload_with_amenities():
    payload = _lang_payload()
    payload['ru_RU']['amenities'] = {
        'cockpit': [{'name': 'Air conditioning'}],
        'entertainment': [{'name': 'SUP board'}],
        'equipment': [{'name': 'Autopilot'}],
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

    @patch('boats.parser._fetch_all_languages_data', return_value=_lang_payload())
    @patch('boats.parser._extract_not_included', return_value=[])
    @patch('boats.parser._extract_delivery_extras', return_value=[])
    @patch('boats.parser._extract_additional_services_from_component', return_value=[])
    @patch('boats.parser._extract_extras_from_component', return_value=[{'name': 'Skipper'}])
    @patch('boats.parser._extract_prices', return_value={})
    @patch('boats.parser._extract_boat_info')
    @patch('boats.parser.extract_pictures', return_value=[])
    @patch('boats.parser.fetch_page', return_value='<html><body>no id in html</body></html>')
    def test_services_only_mode_saves_services_and_amenities(
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
            html_mode='services_only',
        )

        self.assertIsNotNone(result)
        boat = ParsedBoat.objects.get(slug=slug)

        # HTML services are persisted.
        details = BoatDetails.objects.get(boat=boat, language='ru_RU')
        self.assertEqual(details.extras, [{'name': 'Skipper'}])

        # HTML amenities are persisted (empty in this test's mock data).
        self.assertEqual(details.cockpit, [])
        self.assertEqual(details.entertainment, [])
        self.assertEqual(details.equipment, [])

        # BoatDescription is no longer written from HTML in services_only mode.
        self.assertFalse(BoatDescription.objects.filter(boat=boat).exists())

    @patch('boats.parser._fetch_all_languages_data', return_value=_lang_payload_with_amenities())
    @patch('boats.parser._extract_not_included', return_value=[])
    @patch('boats.parser._extract_delivery_extras', return_value=[])
    @patch('boats.parser._extract_additional_services_from_component', return_value=[])
    @patch('boats.parser._extract_extras_from_component', return_value=[{'name': 'Skipper'}])
    @patch('boats.parser._extract_prices', return_value={})
    @patch('boats.parser._extract_boat_info')
    @patch('boats.parser.extract_pictures', return_value=[])
    @patch('boats.parser.fetch_page', return_value='<html><body>no id in html</body></html>')
    def test_services_only_mode_writes_html_amenities(
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
        slug = 'lagoon-50-existing-amenities'
        boat = ParsedBoat.objects.create(
            boat_id='boat-existing-1',
            slug=slug,
            manufacturer='Lagoon',
            model='50',
            year=2021,
        )
        BoatDetails.objects.create(
            boat=boat,
            language='ru_RU',
            cockpit=[{'name': 'Legacy cockpit'}],
            entertainment=[{'name': 'Legacy entertainment'}],
            equipment=[{'name': 'Legacy equipment'}],
            extras=[],
            additional_services=[],
            delivery_extras=[],
            not_included=[],
        )
        mock_boat_info.return_value = {
            'title': 'Lagoon 50 | Existing Amenities',
            'manufacturer': 'Lagoon',
            'model': '50',
            'year': '2021',
        }

        result = parse_boataround_url(
            f'https://www.boataround.com/ru/yachta/{slug}/',
            save_to_db=True,
            html_mode='services_only',
        )

        self.assertIsNotNone(result)
        details = BoatDetails.objects.get(boat=boat, language='ru_RU')
        # Amenities are HTML-owned — updated from HTML even in services_only.
        self.assertEqual(details.extras, [{'name': 'Skipper'}])
        self.assertEqual(details.cockpit, [{'name': 'Air conditioning'}])
        self.assertEqual(details.entertainment, [{'name': 'SUP board'}])
        self.assertEqual(details.equipment, [{'name': 'Autopilot'}])

    @patch('boats.parser._fetch_all_languages_data', return_value=_lang_payload_with_amenities())
    @patch('boats.parser._extract_not_included', return_value=[])
    @patch('boats.parser._extract_delivery_extras', return_value=[])
    @patch('boats.parser._extract_additional_services_from_component', return_value=[])
    @patch('boats.parser._extract_extras_from_component', return_value=[])
    @patch('boats.parser._extract_prices', return_value={})
    @patch('boats.parser._extract_boat_info')
    @patch('boats.parser.extract_pictures', return_value=[])
    @patch('boats.parser.fetch_page', return_value='<html><body>no id in html</body></html>')
    def test_all_html_mode_persists_amenities_and_descriptions(
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
        slug = 'lagoon-42-test-boat'
        mock_boat_info.return_value = {
            'title': 'Lagoon 42 | Test Boat',
            'manufacturer': 'Lagoon',
            'model': '42',
            'year': '2022',
        }

        result = parse_boataround_url(
            f'https://www.boataround.com/ru/yachta/{slug}/',
            save_to_db=True,
            html_mode='all_html',
        )

        self.assertIsNotNone(result)
        boat = ParsedBoat.objects.get(slug=slug)
        details = BoatDetails.objects.get(boat=boat, language='ru_RU')

        self.assertEqual(details.cockpit, [{'name': 'Air conditioning'}])
        self.assertEqual(details.entertainment, [{'name': 'SUP board'}])
        self.assertEqual(details.equipment, [{'name': 'Autopilot'}])
        self.assertTrue(BoatDescription.objects.filter(boat=boat, language='ru_RU').exists())
