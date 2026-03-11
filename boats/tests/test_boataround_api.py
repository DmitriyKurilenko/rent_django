"""Tests for BoataroundAPI network behavior."""
from unittest.mock import Mock, patch
import requests
from django.test import SimpleTestCase, TestCase

from boats.boataround_api import BoataroundAPI, format_boat_data
from boats.models import Charter


class BoataroundAPIPricingTest(SimpleTestCase):
    """Price API should be resilient to transient network failures."""

    @patch("boats.boataround_api.requests.get")
    def test_get_price_retries_on_timeout_and_returns_price(self, mock_get):
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

        mock_get.side_effect = [timeout_error, ok_response]

        result = BoataroundAPI.get_price(
            slug="bali-42-zephyr",
            check_in="2026-03-14",
            check_out="2026-03-21",
            currency="EUR",
            lang="ru_RU",
        )

        self.assertEqual(mock_get.call_count, 2)
        self.assertEqual(result.get("price"), 1234)
        self.assertEqual(result.get("discount_without_additionalExtra"), 7)
        self.assertEqual(result.get("additional_discount"), 3)

    @patch("boats.boataround_api.requests.get")
    def test_get_price_returns_empty_after_all_retries_timeout(self, mock_get):
        mock_get.side_effect = requests.Timeout("read timeout")

        result = BoataroundAPI.get_price(
            slug="bali-42-zephyr",
            check_in="2026-03-14",
            check_out="2026-03-21",
            currency="EUR",
            lang="ru_RU",
        )

        self.assertEqual(result, {})
        self.assertEqual(mock_get.call_count, 3)


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

        # Базовая цена после 10% = 900; + условная extra скидка 5% при комиссии 20 => 855
        self.assertEqual(result.get("price"), 855)
