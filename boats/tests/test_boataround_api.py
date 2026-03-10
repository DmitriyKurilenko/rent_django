"""Tests for BoataroundAPI network behavior."""
from unittest.mock import Mock, patch
import requests
from django.test import SimpleTestCase

from boats.boataround_api import BoataroundAPI


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
