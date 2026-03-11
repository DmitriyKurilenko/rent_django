"""Tests for unified pricing module."""
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, SimpleTestCase

from boats.models import ParsedBoat, BoatPrice, Charter
from boats.pricing import (
    extract_price_components,
    build_price_breakdown,
    resolve_live_or_fallback_price,
)


class PricingExtractionTest(SimpleTestCase):
    def test_extract_price_components_from_search_payload(self):
        payload = {
            "price": 2000,
            "discount": 15,
            "additionalDiscount": 5,
        }
        base_price, discount_without_extra, additional_discount = extract_price_components(payload)
        self.assertEqual(base_price, 2000)
        self.assertEqual(discount_without_extra, 10)
        self.assertEqual(additional_discount, 5)

    def test_build_price_breakdown_applies_discounts_and_old_price(self):
        breakdown = build_price_breakdown(
            base_price=1000,
            discount_without_extra=10,
            additional_discount=0,
            charter=None,
            currency="EUR",
        )
        self.assertEqual(breakdown["base_price"], 1000)
        self.assertEqual(breakdown["final_price"], 900)
        self.assertEqual(breakdown["old_price"], 1000)
        self.assertEqual(breakdown["discount_percent"], 10)

    def test_extract_price_components_prefers_policy_prices_over_unstable_top_level(self):
        payload = {
            "price": 9150,
            "totalPrice": 3650.85,
            "discount": 61,
            "additionalDiscount": 5,
            "policies": [
                {
                    "prices": {
                        "price": 9150,
                        "discount_without_additionalExtra": 60,
                        "additional_discount": 5,
                        "totalPrice": 3477,
                    }
                }
            ],
        }
        base_price, discount_without_extra, additional_discount = extract_price_components(payload)
        self.assertEqual(base_price, 9150)
        self.assertEqual(discount_without_extra, 60)
        self.assertEqual(additional_discount, 5)

    def test_extract_price_components_reconciles_with_total_price_when_policy_missing(self):
        payload = {
            "price": 9150,
            "totalPrice": 3477,
            "discount": 63,
            "discountWithoutAdditional": 58,
            "additionalDiscount": 5,
            "policies": [],
        }

        base_price, discount_without_extra, additional_discount = extract_price_components(payload)

        self.assertEqual(base_price, 9150)
        self.assertEqual(round(discount_without_extra, 2), 60.0)
        self.assertEqual(additional_discount, 5)


class PricingResolverTest(TestCase):
    def setUp(self):
        self.charter = Charter.objects.create(charter_id="charter-1", name="Charter 1", commission=20)
        self.parsed_boat = ParsedBoat.objects.create(
            boat_id="boat-1",
            slug="bali-42-zephyr",
            manufacturer="Bali",
            model="4.2",
            year=2020,
            charter=self.charter,
        )
        BoatPrice.objects.create(
            boat=self.parsed_boat,
            currency="EUR",
            price_per_day=Decimal("1000.00"),
            price_per_week=Decimal("7000.00"),
        )

    @patch("boats.boataround_api.BoataroundAPI.get_price")
    def test_resolver_uses_api_when_available(self, mock_get_price):
        mock_get_price.return_value = {
            "price": 2000,
            "discount_without_additionalExtra": 10,
            "additional_discount": 0,
        }

        quote = resolve_live_or_fallback_price(
            slug=self.parsed_boat.slug,
            check_in="2026-03-14",
            check_out="2026-03-21",
            lang="ru_RU",
            charter=self.charter,
            rental_days=7,
            currency="EUR",
        )

        self.assertEqual(quote["source"], "api")
        self.assertEqual(quote["base_price"], 2000)
        self.assertGreater(quote["final_price"], 0)

    @patch("boats.boataround_api.BoataroundAPI.get_price")
    def test_resolver_falls_back_to_db_when_api_unavailable(self, mock_get_price):
        mock_get_price.return_value = {}

        quote = resolve_live_or_fallback_price(
            slug=self.parsed_boat.slug,
            check_in="2026-03-14",
            check_out="2026-03-21",
            lang="ru_RU",
            charter=self.charter,
            rental_days=7,
            currency="EUR",
        )

        self.assertEqual(quote["source"], "db")
        self.assertEqual(quote["final_price"], 7000)
