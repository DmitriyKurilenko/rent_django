"""Tests for boat detail API view behavior."""
from decimal import Decimal
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from boats.models import ParsedBoat, BoatDescription, BoatPrice, BoatTechnicalSpecs


class BoatDetailPriceNoCacheTest(TestCase):
    """Boat detail should not depend on cached boat_price values."""

    def setUp(self):
        cache.clear()
        self.parsed_boat = ParsedBoat.objects.create(
            boat_id="boat-123",
            slug="bali-42-zephyr",
            manufacturer="Bali",
            model="4.2",
            year=2020,
        )
        BoatDescription.objects.create(
            boat=self.parsed_boat,
            language="ru_RU",
            title="Bali 4.2 | Zephyr",
            description="Test description",
        )
        BoatPrice.objects.create(
            boat=self.parsed_boat,
            currency="EUR",
            price_per_day=Decimal("1000.00"),
        )
        BoatTechnicalSpecs.objects.create(boat=self.parsed_boat)

    @patch("boats.boataround_api.BoataroundAPI.search_by_slug", return_value=None)
    @patch("boats.boataround_api.BoataroundAPI.get_price")
    def test_uses_live_price_even_if_old_price_cache_key_exists(self, mock_get_price, _mock_search_by_slug):
        mock_get_price.return_value = {
            "price": 1400,
            "discount_without_additionalExtra": 10,
            "additional_discount": 0,
        }

        check_in = "2026-03-14"
        check_out = "2026-03-21"
        price_cache_key = f"boat_price:{self.parsed_boat.slug}:{check_in}:{check_out}"
        cache.set(
            price_cache_key,
            {
                "price": 0,
                "discount": 0,
                "total_price": 0,
                "old_price": 0,
                "discount_percent": 0,
                "currency": "EUR",
            },
            60 * 60,
        )

        response = self.client.get(
            reverse("boat_detail_api", kwargs={"boat_id": self.parsed_boat.slug}),
            {"check_in": check_in, "check_out": check_out},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_get_price.call_count, 1)
        self.assertGreater(float(response.context["boat"]["total_price"]), 0)

    @patch("boats.boataround_api.BoataroundAPI.search_by_slug", return_value=None)
    @patch("boats.boataround_api.BoataroundAPI.get_price")
    def test_ignores_unknown_extra_params_when_api_available(self, mock_get_price, _mock_search_by_slug):
        mock_get_price.return_value = {
            "price": 9150,
            "discount_without_additionalExtra": 58,
            "additional_discount": 5,
        }

        response = self.client.get(
            reverse("boat_detail_api", kwargs={"boat_id": self.parsed_boat.slug}),
            {
                "check_in": "2026-03-14",
                "check_out": "2026-03-21",
                "foo_total": "3 477,00",
                "foo_old": "9 150,00",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(float(response.context["boat"]["total_price"]), 3650.85)
        self.assertEqual(float(response.context["boat"]["old_price"]), 9150.0)
        self.assertEqual(int(response.context["boat"]["discount_percent"]), 60)
        self.assertEqual(mock_get_price.call_count, 1)

    @patch("boats.boataround_api.BoataroundAPI.search_by_slug", return_value=None)
    @patch("boats.boataround_api.BoataroundAPI.get_price")
    def test_ignores_unknown_extra_params_when_api_unavailable(self, mock_get_price, _mock_search_by_slug):
        mock_get_price.return_value = {}

        response = self.client.get(
            reverse("boat_detail_api", kwargs={"boat_id": self.parsed_boat.slug}),
            {
                "check_in": "2026-03-14",
                "check_out": "2026-03-21",
                "foo_total": "3 477,00",
                "foo_old": "9 150,00",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(float(response.context["boat"]["total_price"]), 7000.0)
        self.assertEqual(float(response.context["boat"]["old_price"]), 0.0)
        self.assertEqual(int(response.context["boat"]["discount_percent"]), 0)
        self.assertEqual(mock_get_price.call_count, 1)
