"""Tests for boat detail API view behavior."""
from decimal import Decimal
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from boats.models import (
    ParsedBoat,
    BoatDescription,
    BoatPrice,
    BoatTechnicalSpecs,
    BoatDetails,
    BoatGallery,
)


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
        BoatDetails.objects.create(boat=self.parsed_boat, language="ru_RU")
        BoatGallery.objects.create(
            boat=self.parsed_boat,
            cdn_url="https://cdn.example.com/boats/bali-42-zephyr-1.jpg",
            order=1,
        )

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

    @patch("boats.boataround_api.BoataroundAPI.search_by_slug", return_value=None)
    @patch("boats.views.parse_boataround_url")
    @patch("boats.boataround_api.BoataroundAPI.get_price")
    def test_does_not_reparse_when_db_payload_is_complete(
        self,
        mock_get_price,
        mock_parse,
        _mock_search_by_slug,
    ):
        mock_get_price.return_value = {
            "price": 1400,
            "discount_without_additionalExtra": 10,
            "additional_discount": 0,
        }

        response = self.client.get(
            reverse("boat_detail_api", kwargs={"boat_id": self.parsed_boat.slug}),
            {"check_in": "2026-03-14", "check_out": "2026-03-21"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_parse.call_count, 0)

    @patch("boats.boataround_api.BoataroundAPI.search_by_slug", return_value=None)
    @patch("boats.views.parse_boataround_url")
    @patch("boats.boataround_api.BoataroundAPI.get_price")
    def test_invalidates_stale_cached_boat_without_images(
        self,
        mock_get_price,
        mock_parse,
        _mock_search_by_slug,
    ):
        mock_get_price.return_value = {
            "price": 1400,
            "discount_without_additionalExtra": 10,
            "additional_discount": 0,
        }
        cache.set(
            f"boat_data:{self.parsed_boat.slug}:ru_RU",
            {
                "slug": self.parsed_boat.slug,
                "name": "Stale boat",
                "images": [],
                "gallery": [],
                "extras": [],
                "additional_services": [],
                "delivery_extras": [],
                "not_included": [],
                "cockpit": [],
                "entertainment": [],
                "equipment": [],
            },
            60 * 60,
        )

        response = self.client.get(
            reverse("boat_detail_api", kwargs={"boat_id": self.parsed_boat.slug}),
            {"check_in": "2026-03-14", "check_out": "2026-03-21"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_parse.call_count, 0)
        self.assertEqual(
            response.context["boat"]["images"],
            ["https://cdn.example.com/boats/bali-42-zephyr-1.jpg"],
        )


class BoatDetailHydrationTest(TestCase):
    """Boat detail should auto-hydrate incomplete ParsedBoat payload."""

    def setUp(self):
        cache.clear()
        self.parsed_boat = ParsedBoat.objects.create(
            boat_id="boat-456",
            slug="fountaine-pajot-lucia-40-merengue",
            manufacturer="Fountaine Pajot",
            model="Lucia 40",
            year=2021,
        )
        BoatPrice.objects.create(
            boat=self.parsed_boat,
            currency="EUR",
            price_per_day=Decimal("1000.00"),
        )
        BoatTechnicalSpecs.objects.create(boat=self.parsed_boat)

    @patch("boats.views.resolve_live_or_fallback_price")
    @patch("boats.views.parse_boataround_url")
    @patch("boats.boataround_api.BoataroundAPI.search_by_slug", return_value=None)
    def test_auto_reparses_when_gallery_and_details_missing(
        self,
        _mock_search_by_slug,
        mock_parse,
        mock_quote,
    ):
        def parse_side_effect(_url, save_to_db=True):
            self.assertTrue(save_to_db)
            BoatDescription.objects.update_or_create(
                boat=self.parsed_boat,
                language="ru_RU",
                defaults={
                    "title": "Fountaine Pajot Lucia 40 | Merengue",
                    "description": "Auto hydrated description",
                    "location": "Seychelles",
                    "marina": "Eden Island",
                },
            )
            BoatDetails.objects.update_or_create(
                boat=self.parsed_boat,
                language="ru_RU",
                defaults={
                    "extras": [],
                    "additional_services": [],
                    "delivery_extras": [],
                    "not_included": [],
                    "cockpit": [],
                    "entertainment": [],
                    "equipment": [],
                },
            )
            BoatGallery.objects.update_or_create(
                boat=self.parsed_boat,
                order=1,
                defaults={"cdn_url": "https://cdn.example.com/boats/merengue-1.jpg"},
            )
            return {"slug": self.parsed_boat.slug}

        mock_parse.side_effect = parse_side_effect
        mock_quote.return_value = {
            "base_price": 1000.0,
            "discount_without_extra": 0,
            "final_price": 1000.0,
            "old_price": 0.0,
            "discount_percent": 0,
            "currency": "EUR",
            "source": "db",
        }

        response = self.client.get(
            reverse("boat_detail_api", kwargs={"boat_id": self.parsed_boat.slug}),
            {"check_in": "2026-09-05", "check_out": "2026-09-12"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_parse.call_count, 1)
        self.assertEqual(response.context["boat"]["name"], "Fountaine Pajot Lucia 40 | Merengue")
        self.assertEqual(
            response.context["boat"]["images"],
            ["https://cdn.example.com/boats/merengue-1.jpg"],
        )

    @patch("boats.views.parse_boataround_url", return_value=None)
    @patch("boats.boataround_api.BoataroundAPI.search_by_slug", return_value=None)
    def test_returns_explicit_error_when_critical_reparse_fails(
        self,
        _mock_search_by_slug,
        mock_parse,
    ):
        response = self.client.get(
            reverse("boat_detail_api", kwargs={"boat_id": self.parsed_boat.slug}),
            {"check_in": "2026-09-05", "check_out": "2026-09-12"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_parse.call_count, 1)
        self.assertIn("Критическая ошибка данных лодки", response.context["error"])
        self.assertEqual(response.context["boat"]["images"], [])
