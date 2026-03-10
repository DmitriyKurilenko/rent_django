"""Tests for amenities extraction from boat HTML pages."""
from unittest.mock import patch, MagicMock
from django.test import TestCase
from bs4 import BeautifulSoup
import json


class ExtractAmenitiesFromHTMLTest(TestCase):
    """Tests for _extract_amenities_from_html."""

    def _make_soup(self, cockpit_items=None, entertainment_items=None, equipment_items=None):
        """Helper: create BeautifulSoup with <amenities> component."""
        attrs = {}
        if cockpit_items is not None:
            attrs[':cockpit'] = json.dumps(cockpit_items, ensure_ascii=False)
        if entertainment_items is not None:
            attrs[':entertainment'] = json.dumps(entertainment_items, ensure_ascii=False)
        if equipment_items is not None:
            attrs[':equipment'] = json.dumps(equipment_items, ensure_ascii=False)

        attr_str = ' '.join(f'{k}=\'{v}\'' for k, v in attrs.items())
        html = f'<html><body><amenities {attr_str}></amenities></body></html>'
        return BeautifulSoup(html, 'html.parser')

    def test_filters_is_present_false(self):
        """Items with is_present=False must be excluded."""
        from boats.parser import _extract_amenities_from_html
        soup = self._make_soup(cockpit_items=[
            {'name': 'Air conditioning', 'is_present': False, 'icon': 'x', 'index': 0},
            {'name': 'Shower', 'is_present': True, 'icon': 'x', 'index': 1},
        ])
        result = _extract_amenities_from_html(soup)
        self.assertEqual(len(result['cockpit']), 1)
        self.assertEqual(result['cockpit'][0]['name'], 'Shower')

    def test_keeps_is_present_true(self):
        """Items with is_present=True must be included."""
        from boats.parser import _extract_amenities_from_html
        soup = self._make_soup(entertainment_items=[
            {'name': 'SUP board', 'is_present': True, 'icon': 'x', 'index': 0},
            {'name': 'Kayak', 'is_present': True, 'icon': 'x', 'index': 1},
        ])
        result = _extract_amenities_from_html(soup)
        self.assertEqual(len(result['entertainment']), 2)

    def test_all_absent_returns_empty(self):
        """All is_present=False → empty list."""
        from boats.parser import _extract_amenities_from_html
        soup = self._make_soup(equipment_items=[
            {'name': 'Generator', 'is_present': False, 'icon': 'x', 'index': 0},
        ])
        result = _extract_amenities_from_html(soup)
        self.assertEqual(result['equipment'], [])

    def test_no_amenities_component(self):
        """Missing <amenities> tag → empty result."""
        from boats.parser import _extract_amenities_from_html
        soup = BeautifulSoup('<html><body><div>no amenities here</div></body></html>', 'html.parser')
        result = _extract_amenities_from_html(soup)
        self.assertEqual(result, {'cockpit': [], 'entertainment': [], 'equipment': []})

    def test_invalid_json_gracefully_handled(self):
        """Invalid JSON in attribute → empty list for that section."""
        from boats.parser import _extract_amenities_from_html
        html = "<html><body><amenities :cockpit='not valid json'></amenities></body></html>"
        soup = BeautifulSoup(html, 'html.parser')
        result = _extract_amenities_from_html(soup)
        self.assertEqual(result['cockpit'], [])

    def test_result_only_has_name(self):
        """Result items must only contain 'name' key."""
        from boats.parser import _extract_amenities_from_html
        soup = self._make_soup(cockpit_items=[
            {'name': 'Shower', 'is_present': True, 'icon': 'icon-m-shower', 'index': 3},
        ])
        result = _extract_amenities_from_html(soup)
        self.assertEqual(list(result['cockpit'][0].keys()), ['name'])


class FormatBoatDataEquipmentTest(TestCase):
    """format_boat_data must not populate cockpit/entertainment/equipment from search API."""

    def _make_boat(self, filter_data):
        """Helper: minimal boat dict for format_boat_data."""
        return {
            '_id': 'test-id',
            'slug': 'test-slug',
            'title': 'Test Boat',
            'price': {'price': 1000, 'totalPrice': 900, 'discountWithoutExtra': 10, 'additionalDiscount': 5},
            'pictures': [],
            'cabins': 2,
            'berths': 4,
            'length': 12.0,
            'year': 2020,
            'category': 'catamaran',
            'filter': filter_data,
            'coordinates': [],
            'location': 'Turkey',
        }

    def test_cockpit_empty_from_search_api(self):
        """format_boat_data must return empty cockpit even if filter has data."""
        from boats.boataround_api import format_boat_data
        boat = self._make_boat({'cockpit': [{'_id': 'air-condition', 'count': 9000, 'name': 'AC'}]})
        with patch('boats.boataround_api._get_charter', return_value=None):
            result = format_boat_data(boat)
        self.assertEqual(result.get('cockpit', []), [])

    def test_entertainment_empty_from_search_api(self):
        """format_boat_data must return empty entertainment."""
        from boats.boataround_api import format_boat_data
        boat = self._make_boat({'entertainment': [{'_id': 'sup', 'count': 1000, 'name': 'SUP'}]})
        with patch('boats.boataround_api._get_charter', return_value=None):
            result = format_boat_data(boat)
        self.assertEqual(result.get('entertainment', []), [])

    def test_equipment_empty_from_search_api(self):
        """format_boat_data must return empty equipment."""
        from boats.boataround_api import format_boat_data
        boat = self._make_boat({'equipment': [{'_id': 'autopilot', 'count': 5000, 'name': 'Autopilot'}]})
        with patch('boats.boataround_api._get_charter', return_value=None):
            result = format_boat_data(boat)
        self.assertEqual(result.get('equipment', []), [])
