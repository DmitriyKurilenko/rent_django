"""Tests for BoataroundAPI network behavior."""
from unittest.mock import Mock, patch
import requests
from django.test import SimpleTestCase, TestCase

from boats.boataround_api import BoataroundAPI, format_boat_data
from boats.models import Charter


class BoataroundAPIPricingTest(SimpleTestCase):
    """Price API should be resilient to transient network failures."""

    @patch("time.sleep")
    @patch("boats.boataround_api.requests.get")
    def test_get_price_retries_on_timeout_and_returns_price(self, mock_get, _mock_sleep):
        timeout_error = requests.Timeout("read timeout")

        ok_response = Mock()
        ok_response.status_code = 200
        ok_response.json.return_value = {
            "data": [
                {
                    "data": [
                        {
                            "slug": "bali-42-zephyr",
                            "title": "Bali 4.2 | Zephyr",
                            "price": 1234,
                            "totalPrice": 1111,
                            "discount": 10,
                            "policies": [
                                {
                                    "prices": {
                                        "price_id": "abc",
                                        "price": 1234,
                                        "discount_without_additionalExtra": 7,
                                        "additional_discount": 3,
                                    }
                                }
                            ],
                        }
                    ]
                }
            ]
        }

        # _fetch_price_once has 3 internal retries; get_price uses consensus
        # (3 matching totalPrice from up to 5 attempts).
        # Call 1: timeout (internal retry), Call 2: ok (1st result),
        # Call 3: ok (2nd result), Call 4: ok (3rd result = consensus).
        mock_get.side_effect = [timeout_error, ok_response, ok_response, ok_response]

        result = BoataroundAPI.get_price(
            slug="bali-42-zephyr",
            check_in="2026-03-14",
            check_out="2026-03-21",
            currency="EUR",
            lang="ru_RU",
        )

        self.assertEqual(mock_get.call_count, 4)
        self.assertEqual(result.get("price"), 1234)
        self.assertEqual(result.get("discount_without_additionalExtra"), 7)
        self.assertEqual(result.get("additional_discount"), 3)

    @patch("time.sleep")
    @patch("boats.boataround_api.requests.get")
    def test_get_price_returns_empty_after_all_retries_timeout(self, mock_get, _mock_sleep):
        mock_get.side_effect = requests.Timeout("read timeout")

        result = BoataroundAPI.get_price(
            slug="timeout-boat-slug",
            check_in="2025-01-01",
            check_out="2025-01-08",
            currency="EUR",
            lang="ru_RU",
        )

        self.assertEqual(result, {})
        # 5 consensus attempts × 3 internal retries each = 15 calls
        self.assertEqual(mock_get.call_count, 15)


class BoataroundAPISlugMatchTest(SimpleTestCase):
    @patch("boats.boataround_api.requests.get")
    def test_search_by_slug_uses_exact_slug_match(self, mock_get):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {
            "status": "Success",
            "data": [
                {
                    "data": [
                        {"slug": "wrong-boat", "title": "Wrong boat"},
                        {
                            "slug": "bali-44-ediba-libra",
                            "title": "Bali 4.4 | Ediba Libra",
                            "price": 9150,
                            "discount": 62,
                            "policies": [
                                {
                                    "prices": {
                                        "price": 9150,
                                        "discount_without_additionalExtra": 60,
                                        "additional_discount": 5,
                                    }
                                }
                            ],
                        },
                    ]
                }
            ],
        }
        mock_get.return_value = response

        result = BoataroundAPI.search_by_slug("bali-44-ediba-libra")

        self.assertEqual(result.get("slug"), "bali-44-ediba-libra")
        self.assertEqual(result.get("name"), "Bali 4.4 | Ediba Libra")


class BoataroundAPICharterResolutionTest(TestCase):
    def test_format_boat_data_resolves_charter_by_name_when_id_unknown(self):
        Charter.objects.create(
            charter_id="known-charter-id",
            name="MarGeo Yachts",
            commission=20,
        )

        boat = {
            "slug": "lagoon-50-margeo-16",
            "title": "Lagoon 50 | Margeo 16",
            "charter": "MarGeo Yachts",
            "charter_id": "unknown-runtime-id",
            "currency": "EUR",
            "price": 1000,
            "discount": 10,
            "policies": [
                {
                    "prices": {
                        "price": 1000,
                        "discount_without_additionalExtra": 10,
                        "additional_discount": 0,
                    }
                }
            ],
        }

        result = format_boat_data(boat)

        # Аддитивная модель: total_discount = 10 + 0 + min(5, 20) = 15%
        # final = 1000 * (1 - 15/100) = 850
        self.assertEqual(result.get("price"), 850)


class BoataroundAPIPrefetchConsensusTest(SimpleTestCase):
    """Tests for prefetch_search_consensus — 5 search requests → cache price consensus."""

    @patch("time.sleep")
    @patch("boats.boataround_api.BoataroundAPI.search")
    @patch("django.core.cache.cache.set")
    def test_prefetch_makes_5_search_requests(self, mock_cache_set, mock_search, _mock_sleep):
        """prefetch_search_consensus should call search exactly 5 times."""
        mock_search.return_value = {
            'boats': [
                {'slug': 'boat-a', 'totalPrice': 1000, 'price': 1500, 'discount': 33},
                {'slug': 'boat-b', 'totalPrice': 2000, 'price': 2500, 'discount': 20},
            ],
            'total': 2,
            'page': 1,
            'totalPages': 1,
            'filters': {},
        }

        result = BoataroundAPI.prefetch_search_consensus(
            destination='turkey',
            check_in='2026-08-29',
            check_out='2026-09-05',
            slugs=['boat-a', 'boat-b'],
            lang='en_EN',
        )

        self.assertEqual(mock_search.call_count, 5)
        # Each call should have slugs parameter
        for call in mock_search.call_args_list:
            self.assertEqual(call.kwargs.get('slugs'), 'boat-a,boat-b')

    @patch("time.sleep")
    @patch("boats.boataround_api.BoataroundAPI.search")
    @patch("django.core.cache.cache.set")
    def test_prefetch_writes_most_common_totalPrice_to_cache(self, mock_cache_set, mock_search, _mock_sleep):
        """When prices vary across 5 calls, most common should be cached."""
        # Round 1-2: 1000, Round 3-4: 1100, Round 5: 1000
        # Expected: most common = 1000 (3 times)
        # price=1500, additionalDiscount=0, consensus totalPrice=1000
        # dwe = (1 - 1000/1500)*100 - 0 = 33.33
        mock_search.side_effect = [
            {'boats': [{'slug': 'boat-a', 'totalPrice': 1000.0, 'price': 1500.0, 'discount': 33, 'additionalDiscount': 0}]},
            {'boats': [{'slug': 'boat-a', 'totalPrice': 1000.0, 'price': 1500.0, 'discount': 33, 'additionalDiscount': 0}]},
            {'boats': [{'slug': 'boat-a', 'totalPrice': 1100.0, 'price': 1500.0, 'discount': 27, 'additionalDiscount': 0}]},
            {'boats': [{'slug': 'boat-a', 'totalPrice': 1100.0, 'price': 1500.0, 'discount': 27, 'additionalDiscount': 0}]},
            {'boats': [{'slug': 'boat-a', 'totalPrice': 1000.0, 'price': 1500.0, 'discount': 33, 'additionalDiscount': 0}]},
        ]

        BoataroundAPI.prefetch_search_consensus(
            destination='turkey',
            check_in='2026-08-29',
            check_out='2026-09-05',
            slugs=['boat-a'],
            lang='en_EN',
        )

        # Verify cache.set was called with consensus totalPrice = 1000
        cache_calls = [c for c in mock_cache_set.call_args_list]
        self.assertEqual(len(cache_calls), 1)
        call_args = cache_calls[0]
        self.assertEqual(call_args[0][0], 'price_consensus:boat-a:2026-08-29:2026-09-05:EUR')
        self.assertEqual(call_args[0][1]['totalPrice'], 1000.0)
        # Verify computed discount_without_additionalExtra is written
        self.assertIn('discount_without_additionalExtra', call_args[0][1])

    @patch("time.sleep")
    @patch("boats.boataround_api.BoataroundAPI.search")
    @patch("django.core.cache.cache.set")
    def test_prefetch_returns_dict_with_all_slugs(self, mock_cache_set, mock_search, _mock_sleep):
        """Return value should contain consensus dict for each requested slug."""
        mock_search.return_value = {
            'boats': [
                {'slug': 'boat-a', 'totalPrice': 1000.0, 'price': 1500.0, 'discount': 33, 'additionalDiscount': 0},
                {'slug': 'boat-b', 'totalPrice': 2000.0, 'price': 2500.0, 'discount': 20, 'additionalDiscount': 0},
            ],
            'total': 2,
            'page': 1,
            'totalPages': 1,
            'filters': {},
        }

        result = BoataroundAPI.prefetch_search_consensus(
            destination='turkey',
            check_in='2026-08-29',
            check_out='2026-09-05',
            slugs=['boat-a', 'boat-b'],
            lang='en_EN',
        )

        self.assertEqual(set(result.keys()), {'boat-a', 'boat-b'})
        self.assertEqual(result['boat-a']['totalPrice'], 1000.0)
        self.assertEqual(result['boat-b']['totalPrice'], 2000.0)

    @patch("time.sleep")
    @patch("boats.boataround_api.BoataroundAPI.search")
    @patch("django.core.cache.cache.set")
    def test_prefetch_handles_missing_slugs_in_response(self, mock_cache_set, mock_search, _mock_sleep):
        """If search returns fewer boats than requested, missing slugs get no cache entry."""
        mock_search.return_value = {
            'boats': [{'slug': 'boat-a', 'totalPrice': 1000.0, 'price': 1500, 'discount': 33}],
            'total': 1,
            'page': 1,
            'totalPages': 1,
            'filters': {},
        }

        result = BoataroundAPI.prefetch_search_consensus(
            destination='turkey',
            check_in='2026-08-29',
            check_out='2026-09-05',
            slugs=['boat-a', 'boat-b'],  # boat-b not in response
            lang='en_EN',
        )

        # boat-a should be in result, boat-b should not
        self.assertIn('boat-a', result)
        self.assertNotIn('boat-b', result)
        # Only one cache write for boat-a
        cache_calls = [c for c in mock_cache_set.call_args_list]
        self.assertEqual(len(cache_calls), 1)

    @patch("time.sleep")
    @patch("boats.boataround_api.BoataroundAPI.search")
    @patch("django.core.cache.cache.set")
    def test_prefetch_returns_empty_when_no_slugs(self, mock_cache_set, mock_search, _mock_sleep):
        """Empty slugs list → no search calls, empty dict returned."""
        result = BoataroundAPI.prefetch_search_consensus(
            destination='turkey',
            check_in='2026-08-29',
            check_out='2026-09-05',
            slugs=[],
            lang='en_EN',
        )

        self.assertEqual(result, {})
        mock_search.assert_not_called()
        mock_cache_set.assert_not_called()
